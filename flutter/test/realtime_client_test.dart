/// Phase 3C RealtimeClient 完整单元测试（Flutter）。
///
/// 通过注入内存 Fake StreamChannel 驱动真实状态机，覆盖：
/// - 连接生命周期 (connect → connecting → authenticating → ready → connected)
/// - 正常消息收发 / ping-pong / addEventListener
/// - malformed event (非JSON / 数组 / 空对象 / 字段类型错误)
/// - unknown event
/// - missing field (type / payload / id / timestamp)
/// - disconnect (服务端主动关闭 / 客户端 disconnect)
/// - error (stream error / WS_AUTH_FAILED)
/// - reconnect (channel failure → 新 channel → connected)
/// - backoff (1/2/4/8/16s cap + ready 重置)
/// - channel close (disconnect 后无事件 / timer 取消)
/// - connection failure (channelFactory 抛异常)
///
/// 所有测试均驱动真实生产代码并做有效断言，无 skip、无空断言。
library;

import 'dart:async';
import 'dart:convert';

import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:stream_channel/stream_channel.dart';

import 'package:flutter_client/core/realtime/connection_state.dart';
import 'package:flutter_client/core/realtime/event_envelope.dart';
import 'package:flutter_client/core/realtime/realtime_client.dart';

// ============================================================================
// FakeWebSocketSink — 捕获客户端 → 服务端消息
// 实现 StreamSink<dynamic> 完整接口（add / addError / addStream / close / done）
// ============================================================================
class FakeWebSocketSink implements StreamSink<dynamic> {
  final List<dynamic> sent = <dynamic>[];
  bool closed = false;
  final Completer<void> _done = Completer<void>();

  @override
  void add(dynamic data) {
    if (closed) return;
    sent.add(data);
  }

  @override
  void addError(Object error, [StackTrace? stackTrace]) {
    // no-op: 测试中不通过 sink 发错误
  }

  @override
  Future<dynamic> addStream(Stream<dynamic> stream) async {
    await stream.forEach(add);
  }

  @override
  Future<void> close() async {
    closed = true;
    if (!_done.isCompleted) _done.complete();
  }

  @override
  Future<void> get done => _done.future;
}

// ============================================================================
// FakeWebSocketChannel — 内存版 StreamChannel<dynamic>
//
// 严格实现 stream_channel 包的 StreamChannel<T> 抽象接口（仅 stream + sink），
// 不 extends WebSocketChannel（3.x 已改为 abstract interface class，无法合法继承）。
// ============================================================================
class FakeWebSocketChannel with StreamChannelMixin<dynamic> {
  /// 服务端 → 客户端：测试通过 emit/emitError/closeServer 写入，RealtimeClient 从 stream 读取
  final StreamController<dynamic> _incoming = StreamController<dynamic>();

  /// 客户端 → 服务端：RealtimeClient 通过 sink.add 写入，测试通过 sentMessages 读取
  final FakeWebSocketSink _sink = FakeWebSocketSink();

  @override
  Stream<dynamic> get stream => _incoming.stream;

  @override
  StreamSink<dynamic> get sink => _sink;

  // ---- 测试辅助：模拟服务端行为 ----
  void emit(dynamic message) => _incoming.add(message);
  void emitError(Object error) => _incoming.addError(error);
  void closeServer() => _incoming.close();
  bool get isServerClosed => _incoming.isClosed;

  // ---- 测试辅助：检查客户端发出的消息 ----
  List<dynamic> get sentMessages => _sink.sent;
  bool get isSinkClosed => _sink.closed;
}

// ============================================================================
// FakeChannelFactory — 追踪 channelFactory 调用并产出 FakeWebSocketChannel
//
// 方法签名严格匹配 RealtimeClient.channelFactory 的类型：
//   StreamChannel<dynamic> Function(Uri uri, {Map<String, String> headers})
// ============================================================================
class FakeChannelFactory {
  final List<FakeWebSocketChannel> channels = <FakeWebSocketChannel>[];
  final List<Uri> uris = <Uri>[];
  final List<Map<String, String>> headersHistory = <Map<String, String>>[];

  /// 非 null 时，每次调用抛此异常（用于 connection failure 测试）
  Object? throwOnCall;

  int get callCount => channels.length;

  StreamChannel<dynamic> call(Uri uri, {Map<String, String> headers = const <String, String>{}}) {
    uris.add(uri);
    headersHistory.add(Map<String, String>.from(headers));
    if (throwOnCall != null) throw throwOnCall!;
    final channel = FakeWebSocketChannel();
    channels.add(channel);
    return channel;
  }
}

// ============================================================================
// 测试辅助函数
// ============================================================================

/// 构造 connection.ready 事件 JSON
String _readyEvent({String connId = 'conn_1'}) => jsonEncode(<String, dynamic>{
      'type': 'connection.ready',
      'id': 'evt_ready_001',
      'timestamp': '2026-01-01T00:00:00Z',
      'payload': <String, dynamic>{'connection_id': connId},
    });

/// 构造 connection.ping 事件 JSON
String _pingEvent() => jsonEncode(<String, dynamic>{
      'type': 'connection.ping',
      'id': 'evt_ping_001',
      'timestamp': '2026-01-01T00:00:01Z',
      'payload': <String, dynamic>{},
    });

/// 刷新微任务队列（StreamController 事件以微任务投递）
Future<void> _flush() => Future<void>.delayed(Duration.zero);

// ============================================================================
// 测试主体
// ============================================================================
void main() {
  // ------------------------------------------------------------------
  // Group 1: Connection Lifecycle
  // ------------------------------------------------------------------
  group('Connection Lifecycle', () {
    test('connect 驱动真实状态转换 connecting→authenticating→ready→connected', () async {
      final states = <ConnectionState>[];
      final factory = FakeChannelFactory();
      final client = RealtimeClient(
        baseUrl: 'http://127.0.0.1:8000',
        getToken: () => 'test-token',
        onTokenExpired: () async => false,
        onStateChange: states.add,
        channelFactory: factory.call,
      );
      addTearDown(client.disconnect);

      // 初始状态
      expect(client.state, ConnectionState.disconnected);

      client.connect();
      await _flush();

      // channelFactory 被真实调用
      expect(factory.callCount, 1);
      // 状态经过 connecting → authenticating（_setState 去重，初始 disconnected 不重复）
      expect(states, containsAllInOrder(<ConnectionState>[
        ConnectionState.connecting,
        ConnectionState.authenticating,
      ]));
      expect(client.state, ConnectionState.authenticating);
      // Authorization header 正确注入
      expect(factory.headersHistory.last['Authorization'], 'Bearer test-token');

      // 服务端发出 connection.ready → 真实状态转换到 connected
      factory.channels.first.emit(_readyEvent());
      await _flush();

      expect(client.state, ConnectionState.connected);
      expect(states.last, ConnectionState.connected);
      // connected 之前必须经过 authenticating
      expect(states.indexOf(ConnectionState.authenticating), lessThan(states.indexOf(ConnectionState.connected)));
    });

    test('connect 时 token 为 null → error 状态且不创建 channel', () async {
      final states = <ConnectionState>[];
      final factory = FakeChannelFactory();
      final client = RealtimeClient(
        baseUrl: 'http://test',
        getToken: () => null,
        onTokenExpired: () async => false,
        onStateChange: states.add,
        channelFactory: factory.call,
      );
      addTearDown(client.disconnect);

      client.connect();
      await _flush();

      expect(factory.callCount, 0); // 没有 token 时不调用 channelFactory
      expect(client.state, ConnectionState.error);
    });

    test('重复调用 connect() 不产生重复 channel（_running 守卫）', () async {
      final factory = FakeChannelFactory();
      final client = RealtimeClient(
        baseUrl: 'http://test',
        getToken: () => 'tok',
        onTokenExpired: () async => false,
        channelFactory: factory.call,
      );
      addTearDown(client.disconnect);

      client.connect();
      client.connect(); // 第二次应为 no-op
      await _flush();

      expect(factory.callCount, 1);
    });

    test('baseUrl https → wss 协议转换正确', () async {
      final factory = FakeChannelFactory();
      final client = RealtimeClient(
        baseUrl: 'https://api.example.com',
        getToken: () => 'tok',
        onTokenExpired: () async => false,
        channelFactory: factory.call,
      );
      addTearDown(client.disconnect);

      client.connect();
      await _flush();

      expect(factory.uris.last.scheme, 'wss');
      expect(factory.uris.last.host, 'api.example.com');
      expect(factory.uris.last.path, '/ws/v1');
    });
  });

  // ------------------------------------------------------------------
  // Group 2: Normal Message 收发
  // ------------------------------------------------------------------
  group('Normal Message收发', () {
    test('接收合法事件并分发 type/id/timestamp/payload 全部字段', () async {
      final events = <EventEnvelope>[];
      final factory = FakeChannelFactory();
      final client = RealtimeClient(
        baseUrl: 'http://test',
        getToken: () => 'tok',
        onTokenExpired: () async => false,
        onEvent: events.add,
        channelFactory: factory.call,
      );
      addTearDown(client.disconnect);

      client.connect();
      factory.channels.first.emit(_readyEvent());
      await _flush();
      events.clear(); // 丢弃 ready 事件

      factory.channels.first.emit(jsonEncode(<String, dynamic>{
        'type': 'message.new',
        'id': 'msg_001',
        'timestamp': '2026-01-01T00:00:00Z',
        'payload': <String, dynamic>{
          'text': 'hello world',
          'conversation_id': 'conv_abc',
          'sender_id': 'user_1',
        },
      }));
      await _flush();

      expect(events.length, 1);
      final msg = events.first;
      expect(msg.type, 'message.new');
      expect(msg.id, 'msg_001');
      expect(msg.timestamp, '2026-01-01T00:00:00Z');
      expect(msg.payload['text'], 'hello world');
      expect(msg.payload['conversation_id'], 'conv_abc');
      expect(msg.payload['sender_id'], 'user_1');
    });

    test('addEventListener 接收事件且 unsubscribe 后不再接收', () async {
      final events = <EventEnvelope>[];
      final factory = FakeChannelFactory();
      final client = RealtimeClient(
        baseUrl: 'http://test',
        getToken: () => 'tok',
        onTokenExpired: () async => false,
        channelFactory: factory.call,
      );
      addTearDown(client.disconnect);

      final unsubscribe = client.addEventListener(events.add);

      client.connect();
      factory.channels.first.emit(_readyEvent());
      await _flush();
      expect(events.length, 1);
      expect(events.first.type, 'connection.ready');

      // 取消订阅后不再接收
      unsubscribe();
      factory.channels.first.emit(jsonEncode(<String, dynamic>{'type': 'other.event'}));
      await _flush();
      expect(events.length, 1); // 没有新增
    });

    test('connection.ping 触发客户端回 connection.pong', () async {
      final factory = FakeChannelFactory();
      final client = RealtimeClient(
        baseUrl: 'http://test',
        getToken: () => 'tok',
        onTokenExpired: () async => false,
        channelFactory: factory.call,
      );
      addTearDown(client.disconnect);

      client.connect();
      factory.channels.first.emit(_readyEvent());
      await _flush();
      expect(factory.channels.first.sentMessages, isEmpty);

      factory.channels.first.emit(_pingEvent());
      await _flush();

      expect(factory.channels.first.sentMessages.length, 1);
      final decoded = jsonDecode(factory.channels.first.sentMessages.first as String) as Map<String, dynamic>;
      expect(decoded['type'], 'connection.pong');
    });

    test('send() 在已连接时通过 sink 发出 JSON', () async {
      final factory = FakeChannelFactory();
      final client = RealtimeClient(
        baseUrl: 'http://test',
        getToken: () => 'tok',
        onTokenExpired: () async => false,
        channelFactory: factory.call,
      );
      addTearDown(client.disconnect);

      client.connect();
      factory.channels.first.emit(_readyEvent());
      await _flush();

      client.send(<String, dynamic>{'type': 'message.send', 'payload': <String, dynamic>{'text': 'hi'}});
      await _flush();

      expect(factory.channels.first.sentMessages.length, 1);
      final decoded = jsonDecode(factory.channels.first.sentMessages.first as String) as Map<String, dynamic>;
      expect(decoded['type'], 'message.send');
      expect(decoded['payload']['text'], 'hi');
    });
  });

  // ------------------------------------------------------------------
  // Group 3: Malformed Event
  // ------------------------------------------------------------------
  group('Malformed Event', () {
    late RealtimeClient client;
    late FakeChannelFactory factory;
    late List<EventEnvelope> events;

    setUp(() async {
      events = <EventEnvelope>[];
      factory = FakeChannelFactory();
      client = RealtimeClient(
        baseUrl: 'http://test',
        getToken: () => 'tok',
        onTokenExpired: () async => false,
        onEvent: events.add,
        channelFactory: factory.call,
      );
      client.connect();
      factory.channels.first.emit(_readyEvent());
      await _flush();
      events.clear();
    });

    tearDown(() => client.disconnect());

    test('非 JSON 字符串被静默忽略，客户端不崩溃', () async {
      factory.channels.first.emit('not-json-at-all');
      await _flush();

      expect(events, isEmpty);
      expect(client.state, ConnectionState.connected);
      // 后续仍能正常接收合法消息
      factory.channels.first.emit(jsonEncode(<String, dynamic>{'type': 'recovery.event'}));
      await _flush();
      expect(events.last.type, 'recovery.event');
    });

    test('JSON 数组 [] 被静默忽略（cast to Map 失败）', () async {
      factory.channels.first.emit('[]');
      await _flush();

      expect(events, isEmpty);
      expect(client.state, ConnectionState.connected);
    });

    test('空对象 {} 产生 type 为空字符串的 envelope，不崩溃', () async {
      factory.channels.first.emit('{}');
      await _flush();

      expect(events.length, 1);
      expect(events.first.type, '');
      expect(events.first.payload, isEmpty);
      expect(client.state, ConnectionState.connected);
    });

    test('DEFECT-001 回归：type 为 int/object/array 时视为 malformed 静默忽略，无 uncaught error',
        () async {
      // 修复后：EventEnvelope.fromJson 对非 null 且非 String 的 type 抛出 FormatException，
      // RealtimeClient._onMessage 用 on FormatException 捕获并 return（静默忽略），
      // 不再让 TypeError 逃逸到 stream zone。
      final uncaughtErrors = <Object>[];

      await runZonedGuarded(() async {
        final localEvents = <EventEnvelope>[];
        final localFactory = FakeChannelFactory();
        final localClient = RealtimeClient(
          baseUrl: 'http://test',
          getToken: () => 'tok',
          onTokenExpired: () async => false,
          onEvent: localEvents.add,
          channelFactory: localFactory.call,
        );

        localClient.connect();
        localFactory.channels.first.emit(_readyEvent());
        await _flush();
        localEvents.clear();

        // Case 1: type 为 int
        localFactory.channels.first.emit('{"type": 123}');
        await _flush();
        expect(localEvents, isEmpty, reason: 'type:int 应被视为 malformed 静默忽略');
        expect(localClient.state, ConnectionState.connected);

        // Case 3: type 为 object
        localFactory.channels.first.emit('{"type": {"nested": true}}');
        await _flush();
        expect(localEvents, isEmpty, reason: 'type:object 应被视为 malformed 静默忽略');
        expect(localClient.state, ConnectionState.connected);

        // Case 4: type 为 array
        localFactory.channels.first.emit('{"type": [1, 2, 3]}');
        await _flush();
        expect(localEvents, isEmpty, reason: 'type:array 应被视为 malformed 静默忽略');
        expect(localClient.state, ConnectionState.connected);

        localClient.disconnect();
      }, (Object error, StackTrace stack) {
        uncaughtErrors.add(error);
      });

      // 核心断言：修复后不应有任何 uncaught error 逃逸到 zone
      expect(uncaughtErrors, isEmpty, reason: '修复后 type 字段类型错误不应产生 uncaught error');
    });

    test('DEFECT-001 回归：type 为 null 时兼容默认空字符串（既有行为不变）', () async {
      // type 为 null（字段缺失）时，EventEnvelope.fromJson 兼容为 type=''，
      // 与空对象 {} 的行为一致，不视为 malformed。
      factory.channels.first.emit('{"type": null, "payload": {"a": 1}}');
      await _flush();

      expect(events.length, 1);
      expect(events.first.type, '');
      expect(events.first.payload['a'], 1);
      expect(client.state, ConnectionState.connected);
    });

    test('DEFECT-001 回归：malformed event 后后续合法消息仍正常处理（post-error recovery）',
        () async {
      // 这是本缺陷最重要的回归验证：非法消息不能影响后续合法消息处理。
      final uncaughtErrors = <Object>[];

      await runZonedGuarded(() async {
        final localEvents = <EventEnvelope>[];
        final localFactory = FakeChannelFactory();
        final localClient = RealtimeClient(
          baseUrl: 'http://test',
          getToken: () => 'tok',
          onTokenExpired: () async => false,
          onEvent: localEvents.add,
          channelFactory: localFactory.call,
        );

        localClient.connect();
        localFactory.channels.first.emit(_readyEvent());
        await _flush();
        localEvents.clear();

        // 步骤 1：发送 malformed event（type 为 int）
        localFactory.channels.first.emit('{"type": 123}');
        await _flush();

        // 步骤 2：验证客户端存活，状态仍为 connected
        expect(localClient.state, ConnectionState.connected);
        expect(localEvents, isEmpty); // malformed 未被分发

        // 步骤 3：发送合法事件
        localFactory.channels.first.emit(jsonEncode(<String, dynamic>{
          'type': 'message.new',
          'id': 'msg_after_malformed',
          'payload': <String, dynamic>{'text': 'still works'},
        }));
        await _flush();

        // 步骤 4：验证合法事件被正确处理
        expect(localEvents.length, 1);
        expect(localEvents.first.type, 'message.new');
        expect(localEvents.first.id, 'msg_after_malformed');
        expect(localEvents.first.payload['text'], 'still works');

        // 步骤 5：再发一个合法事件确认持续正常
        localFactory.channels.first.emit(jsonEncode(<String, dynamic>{'type': 'second.valid'}));
        await _flush();
        expect(localEvents.length, 2);
        expect(localEvents.last.type, 'second.valid');

        localClient.disconnect();
      }, (Object error, StackTrace stack) {
        uncaughtErrors.add(error);
      });

      expect(uncaughtErrors, isEmpty, reason: '整个过程不应有 uncaught error');
    });

    test('DEFECT-002 回归：id/timestamp 为非 String 类型时视为 malformed，无 uncaught error',
        () async {
      // 修复后：EventEnvelope.fromJson 对 id/timestamp 字段做 is! String 检查，
      // 非 null 且非 String 时抛出 FormatException，由 _onMessage 捕获静默忽略。
      final uncaughtErrors = <Object>[];

      await runZonedGuarded(() async {
        final localEvents = <EventEnvelope>[];
        final localFactory = FakeChannelFactory();
        final localClient = RealtimeClient(
          baseUrl: 'http://test',
          getToken: () => 'tok',
          onTokenExpired: () async => false,
          onEvent: localEvents.add,
          channelFactory: localFactory.call,
        );

        localClient.connect();
        localFactory.channels.first.emit(_readyEvent());
        await _flush();
        localEvents.clear();

        // id 为 int
        localFactory.channels.first.emit('{"type": "message.new", "id": 123}');
        await _flush();
        expect(localEvents, isEmpty, reason: 'id:int 应被视为 malformed');
        expect(localClient.state, ConnectionState.connected);

        // id 为 object
        localFactory.channels.first.emit('{"type": "message.new", "id": {"x": 1}}');
        await _flush();
        expect(localEvents, isEmpty, reason: 'id:object 应被视为 malformed');

        // id 为 array
        localFactory.channels.first.emit('{"type": "message.new", "id": [1, 2]}');
        await _flush();
        expect(localEvents, isEmpty, reason: 'id:array 应被视为 malformed');

        // timestamp 为 int
        localFactory.channels.first.emit('{"type": "message.new", "timestamp": 123456}');
        await _flush();
        expect(localEvents, isEmpty, reason: 'timestamp:int 应被视为 malformed');

        // timestamp 为 object
        localFactory.channels.first.emit('{"type": "message.new", "timestamp": {"nested": true}}');
        await _flush();
        expect(localEvents, isEmpty, reason: 'timestamp:object 应被视为 malformed');

        // timestamp 为 array
        localFactory.channels.first.emit('{"type": "message.new", "timestamp": [1, 2, 3]}');
        await _flush();
        expect(localEvents, isEmpty, reason: 'timestamp:array 应被视为 malformed');
        expect(localClient.state, ConnectionState.connected);

        localClient.disconnect();
      }, (Object error, StackTrace stack) {
        uncaughtErrors.add(error);
      });

      expect(uncaughtErrors, isEmpty, reason: 'id/timestamp 字段类型错误不应产生 uncaught error');
    });

    test('DEFECT-002 回归：id/timestamp 为 null 时兼容默认空字符串（既有行为不变）', () async {
      // id/timestamp 为 null（字段缺失）时，EventEnvelope.fromJson 兼容为默认 ''，
      // 与缺失字段的行为一致，不视为 malformed。
      factory.channels.first.emit(jsonEncode(<String, dynamic>{
        'type': 'message.new',
        'id': null,
        'timestamp': null,
        'payload': <String, dynamic>{'text': 'hi'},
      }));
      await _flush();

      expect(events.length, 1);
      expect(events.first.type, 'message.new');
      expect(events.first.id, '');
      expect(events.first.timestamp, '');
      expect(events.first.payload['text'], 'hi');
      expect(client.state, ConnectionState.connected);
    });

    test('DEFECT-003 回归：payload 为非 Map 类型时视为 malformed，无 uncaught error', () async {
      // 修复后：EventEnvelope.fromJson 对 payload 字段做 is! Map<String, dynamic> 检查，
      // 非 null 且非 Map 时抛出 FormatException，由 _onMessage 捕获静默忽略。
      final uncaughtErrors = <Object>[];

      await runZonedGuarded(() async {
        final localEvents = <EventEnvelope>[];
        final localFactory = FakeChannelFactory();
        final localClient = RealtimeClient(
          baseUrl: 'http://test',
          getToken: () => 'tok',
          onTokenExpired: () async => false,
          onEvent: localEvents.add,
          channelFactory: localFactory.call,
        );

        localClient.connect();
        localFactory.channels.first.emit(_readyEvent());
        await _flush();
        localEvents.clear();

        // payload 为 int
        localFactory.channels.first.emit('{"type": "message.new", "payload": 123}');
        await _flush();
        expect(localEvents, isEmpty, reason: 'payload:int 应被视为 malformed');
        expect(localClient.state, ConnectionState.connected);

        // payload 为 string
        localFactory.channels.first.emit('{"type": "message.new", "payload": "not-a-map"}');
        await _flush();
        expect(localEvents, isEmpty, reason: 'payload:string 应被视为 malformed');

        // payload 为 array
        localFactory.channels.first.emit('{"type": "message.new", "payload": [1, 2, 3]}');
        await _flush();
        expect(localEvents, isEmpty, reason: 'payload:array 应被视为 malformed');

        // payload 为 bool
        localFactory.channels.first.emit('{"type": "message.new", "payload": true}');
        await _flush();
        expect(localEvents, isEmpty, reason: 'payload:bool 应被视为 malformed');
        expect(localClient.state, ConnectionState.connected);

        localClient.disconnect();
      }, (Object error, StackTrace stack) {
        uncaughtErrors.add(error);
      });

      expect(uncaughtErrors, isEmpty, reason: 'payload 字段类型错误不应产生 uncaught error');
    });

    test('DEFECT-003 回归：payload 为 null 时兼容默认空 Map（既有行为不变）', () async {
      // payload 为 null（字段缺失）时，EventEnvelope.fromJson 兼容为默认 {}，
      // 与缺失字段的行为一致，不视为 malformed。
      factory.channels.first.emit(jsonEncode(<String, dynamic>{
        'type': 'message.new',
        'id': 'msg_001',
        'payload': null,
      }));
      await _flush();

      expect(events.length, 1);
      expect(events.first.type, 'message.new');
      expect(events.first.id, 'msg_001');
      expect(events.first.payload, isEmpty);
      expect(client.state, ConnectionState.connected);
    });

    test('DEFECT-002/003 回归：全字段 malformed 后后续合法消息仍正常处理', () async {
      // 综合验证：id/timestamp/payload 任意字段类型错误后，客户端不崩溃，
      // 后续合法消息仍可正常处理。
      final uncaughtErrors = <Object>[];

      await runZonedGuarded(() async {
        final localEvents = <EventEnvelope>[];
        final localFactory = FakeChannelFactory();
        final localClient = RealtimeClient(
          baseUrl: 'http://test',
          getToken: () => 'tok',
          onTokenExpired: () async => false,
          onEvent: localEvents.add,
          channelFactory: localFactory.call,
        );

        localClient.connect();
        localFactory.channels.first.emit(_readyEvent());
        await _flush();
        localEvents.clear();

        // 连续发送多种全字段 malformed 事件
        localFactory.channels.first.emit('{"type": "message.new", "id": 123}');
        await _flush();
        localFactory.channels.first.emit('{"type": "message.new", "timestamp": {}}');
        await _flush();
        localFactory.channels.first.emit('{"type": "message.new", "payload": "bad"}');
        await _flush();
        localFactory.channels.first.emit('{"type": "message.new", "id": [], "payload": 42}');
        await _flush();

        // 验证客户端存活，所有 malformed 均未分发
        expect(localClient.state, ConnectionState.connected);
        expect(localEvents, isEmpty);

        // 发送合法事件
        localFactory.channels.first.emit(jsonEncode(<String, dynamic>{
          'type': 'message.new',
          'id': 'msg_recovery',
          'timestamp': '2026-01-01T00:00:00Z',
          'payload': <String, dynamic>{'text': 'recovered'},
        }));
        await _flush();

        // 验证合法事件被正确处理
        expect(localEvents.length, 1);
        expect(localEvents.first.type, 'message.new');
        expect(localEvents.first.id, 'msg_recovery');
        expect(localEvents.first.timestamp, '2026-01-01T00:00:00Z');
        expect(localEvents.first.payload['text'], 'recovered');

        localClient.disconnect();
      }, (Object error, StackTrace stack) {
        uncaughtErrors.add(error);
      });

      expect(uncaughtErrors, isEmpty, reason: '全字段 malformed 不应产生 uncaught error');
    });
  });

  // ------------------------------------------------------------------
  // Group 4: Unknown Event
  // ------------------------------------------------------------------
  group('Unknown Event', () {
    test('未知 event type 被分发到 onEvent 但不改变连接状态', () async {
      final events = <EventEnvelope>[];
      final states = <ConnectionState>[];
      final factory = FakeChannelFactory();
      final client = RealtimeClient(
        baseUrl: 'http://test',
        getToken: () => 'tok',
        onTokenExpired: () async => false,
        onEvent: events.add,
        onStateChange: states.add,
        channelFactory: factory.call,
      );
      addTearDown(client.disconnect);

      client.connect();
      factory.channels.first.emit(_readyEvent());
      await _flush();
      final stateCountAfterReady = states.length;
      events.clear();

      factory.channels.first.emit(jsonEncode(<String, dynamic>{
        'type': 'unknown.event.xyz',
        'id': 'evt_unk_001',
        'payload': <String, dynamic>{'foo': 'bar'},
      }));
      await _flush();

      // 事件被分发
      expect(events.length, 1);
      expect(events.first.type, 'unknown.event.xyz');
      expect(events.first.payload['foo'], 'bar');
      // 状态不变（switch 无匹配 case，不触发 _setState）
      expect(client.state, ConnectionState.connected);
      expect(states.length, stateCountAfterReady);
    });
  });

  // ------------------------------------------------------------------
  // Group 5: Missing Field
  // ------------------------------------------------------------------
  group('Missing Field', () {
    late RealtimeClient client;
    late FakeChannelFactory factory;
    late List<EventEnvelope> events;

    setUp(() async {
      events = <EventEnvelope>[];
      factory = FakeChannelFactory();
      client = RealtimeClient(
        baseUrl: 'http://test',
        getToken: () => 'tok',
        onTokenExpired: () async => false,
        onEvent: events.add,
        channelFactory: factory.call,
      );
      client.connect();
      factory.channels.first.emit(_readyEvent());
      await _flush();
      events.clear();
    });

    tearDown(() => client.disconnect());

    test('缺少 type 字段 → 默认空字符串，不崩溃', () async {
      factory.channels.first.emit(jsonEncode(<String, dynamic>{
        'id': 'x',
        'payload': <String, dynamic>{'a': 1},
      }));
      await _flush();

      expect(events.length, 1);
      expect(events.first.type, '');
      expect(events.first.payload['a'], 1);
    });

    test('缺少 payload 字段 → 默认空 Map', () async {
      factory.channels.first.emit(jsonEncode(<String, dynamic>{'type': 'test.event'}));
      await _flush();

      expect(events.length, 1);
      expect(events.first.type, 'test.event');
      expect(events.first.payload, isEmpty);
    });

    test('缺少 id 和 timestamp → 默认空字符串', () async {
      factory.channels.first.emit(jsonEncode(<String, dynamic>{
        'type': 'minimal.event',
        'payload': <String, dynamic>{},
      }));
      await _flush();

      expect(events.first.id, '');
      expect(events.first.timestamp, '');
    });
  });

  // ------------------------------------------------------------------
  // Group 6: Disconnect
  // ------------------------------------------------------------------
  group('Disconnect', () {
    test('服务端主动关闭 channel → disconnected 且调度 reconnect', () async {
      final states = <ConnectionState>[];
      final factory = FakeChannelFactory();
      final client = RealtimeClient(
        baseUrl: 'http://test',
        getToken: () => 'tok',
        onTokenExpired: () async => false,
        onStateChange: states.add,
        channelFactory: factory.call,
      );
      addTearDown(client.disconnect);

      client.connect();
      factory.channels.first.emit(_readyEvent());
      await _flush();
      expect(client.state, ConnectionState.connected);

      // 服务端关闭 → stream onDone → _onDrop
      factory.channels.first.closeServer();
      await _flush();

      // 当前实现：_onDrop 始终设 disconnected，然后 _scheduleReconnect
      // （reconnecting 状态在 timer 触发 _open 时才出现）
      expect(client.state, ConnectionState.disconnected);
      expect(states.last, ConnectionState.disconnected);
    });

    test('客户端 disconnect() 关闭 channel sink 并设 disconnected', () async {
      final factory = FakeChannelFactory();
      final client = RealtimeClient(
        baseUrl: 'http://test',
        getToken: () => 'tok',
        onTokenExpired: () async => false,
        channelFactory: factory.call,
      );

      client.connect();
      factory.channels.first.emit(_readyEvent());
      await _flush();
      expect(client.state, ConnectionState.connected);

      client.disconnect();
      await _flush();

      expect(client.state, ConnectionState.disconnected);
      expect(factory.channels.first.isSinkClosed, isTrue);
    });
  });

  // ------------------------------------------------------------------
  // Group 7: Error
  // ------------------------------------------------------------------
  group('Error', () {
    test('stream addError → _onDrop → disconnected + 调度 reconnect', () async {
      final states = <ConnectionState>[];
      final factory = FakeChannelFactory();
      final client = RealtimeClient(
        baseUrl: 'http://test',
        getToken: () => 'tok',
        onTokenExpired: () async => false,
        onStateChange: states.add,
        channelFactory: factory.call,
      );
      addTearDown(client.disconnect);

      client.connect();
      factory.channels.first.emit(_readyEvent());
      await _flush();
      expect(client.state, ConnectionState.connected);

      factory.channels.first.emitError(Exception('connection reset by peer'));
      await _flush();

      // onError → _onDrop（cancelOnError: false 不影响，因为 _onDrop 主动 cancel）
      expect(client.state, ConnectionState.disconnected);
    });

    test('connection.error WS_AUTH_FAILED 触发 token refresh 流程', () async {
      var refreshCalled = false;
      final factory = FakeChannelFactory();
      final client = RealtimeClient(
        baseUrl: 'http://test',
        getToken: () => 'expired-token',
        onTokenExpired: () async {
          refreshCalled = true;
          return false; // refresh 失败
        },
        channelFactory: factory.call,
      );
      addTearDown(client.disconnect);

      client.connect();
      factory.channels.first.emit(_readyEvent());
      await _flush();

      factory.channels.first.emit(jsonEncode(<String, dynamic>{
        'type': 'connection.error',
        'payload': <String, dynamic>{'code': 'WS_AUTH_FAILED'},
      }));
      await _flush();
      await _flush(); // _tryRefreshThenReconnect 是 async，多刷一次

      expect(refreshCalled, isTrue);
      // refresh 失败 → _setState(error) + _scheduleReconnect
      expect(client.state, ConnectionState.error);
    });
  });

  // ------------------------------------------------------------------
  // Group 8: Reconnect
  // ------------------------------------------------------------------
  group('Reconnect', () {
    test('channel 失败 → 等待 backoff → 新 channel → 重新 connected', () async {
      final states = <ConnectionState>[];
      final factory = FakeChannelFactory();
      final client = RealtimeClient(
        baseUrl: 'http://test',
        getToken: () => 'tok',
        onTokenExpired: () async => false,
        onStateChange: states.add,
        channelFactory: factory.call,
      );
      addTearDown(client.disconnect);

      // 初始连接
      client.connect();
      factory.channels.first.emit(_readyEvent());
      await _flush();
      expect(client.state, ConnectionState.connected);
      expect(factory.callCount, 1);

      // channel 失败
      factory.channels.first.closeServer();
      await _flush();
      expect(client.state, ConnectionState.disconnected);

      // 等待首次 backoff (1s) + 余量
      await Future<void>.delayed(const Duration(seconds: 1, milliseconds: 200));

      // channelFactory 被重新调用
      expect(factory.callCount, 2);
      // _open 中 _reconnectAttempts>0 → reconnecting → authenticating
      expect(client.state, ConnectionState.authenticating);
      expect(states, contains(ConnectionState.reconnecting));

      // 新 channel 发出 ready → 重新 connected
      factory.channels.last.emit(_readyEvent(connId: 'conn_2'));
      await _flush();
      expect(client.state, ConnectionState.connected);

      // 确认使用的是新 channel（旧 channel 已被 _onDrop 关闭）
      expect(factory.channels.first.isSinkClosed, isTrue);
    });
  });

  // ------------------------------------------------------------------
  // Group 9: Backoff
  // ------------------------------------------------------------------
  group('Backoff', () {
    test('连续失败遵循 1/2/4/8/16s 退避序列，第 6 次起 cap 在 16s', () {
      FakeAsync().run((FakeAsync async) {
        final factory = FakeChannelFactory();
        final client = RealtimeClient(
          baseUrl: 'http://test',
          getToken: () => 'tok',
          onTokenExpired: () async => false,
          channelFactory: factory.call,
        );

        // 初始连接（不发 ready，保持 authenticating，这样 _reconnectAttempts 不会被重置）
        client.connect();
        async.flushMicrotasks();
        expect(factory.callCount, 1);
        expect(client.state, ConnectionState.authenticating);

        // ---- Drop #1 → backoff 1s ----
        factory.channels.last.closeServer();
        async.flushMicrotasks();
        expect(client.state, ConnectionState.disconnected);

        async.elapse(const Duration(milliseconds: 999));
        expect(factory.callCount, 1, reason: '999ms 时不应触发首次重连');
        async.elapse(const Duration(milliseconds: 2));
        expect(factory.callCount, 2, reason: '~1s 时应触发首次重连');
        async.flushMicrotasks();

        // ---- Drop #2 → backoff 2s ----
        factory.channels.last.closeServer();
        async.flushMicrotasks();
        async.elapse(const Duration(seconds: 1));
        expect(factory.callCount, 2, reason: '1s 时不应触发第二次重连（需 2s）');
        async.elapse(const Duration(seconds: 1));
        expect(factory.callCount, 3, reason: '~2s 时应触发第二次重连');
        async.flushMicrotasks();

        // ---- Drop #3 → backoff 4s ----
        factory.channels.last.closeServer();
        async.flushMicrotasks();
        async.elapse(const Duration(seconds: 3));
        expect(factory.callCount, 3);
        async.elapse(const Duration(seconds: 1));
        expect(factory.callCount, 4, reason: '~4s 时应触发第三次重连');
        async.flushMicrotasks();

        // ---- Drop #4 → backoff 8s ----
        factory.channels.last.closeServer();
        async.flushMicrotasks();
        async.elapse(const Duration(seconds: 7));
        expect(factory.callCount, 4);
        async.elapse(const Duration(seconds: 1));
        expect(factory.callCount, 5, reason: '~8s 时应触发第四次重连');
        async.flushMicrotasks();

        // ---- Drop #5 → backoff 16s ----
        factory.channels.last.closeServer();
        async.flushMicrotasks();
        async.elapse(const Duration(seconds: 15));
        expect(factory.callCount, 5);
        async.elapse(const Duration(seconds: 1));
        expect(factory.callCount, 6, reason: '~16s 时应触发第五次重连');
        async.flushMicrotasks();

        // ---- Drop #6 → cap at 16s（不是 32s）----
        factory.channels.last.closeServer();
        async.flushMicrotasks();
        async.elapse(const Duration(seconds: 15));
        expect(factory.callCount, 6);
        async.elapse(const Duration(seconds: 1));
        expect(factory.callCount, 7, reason: '第 6 次应 cap 在 16s，而非 32s');

        client.disconnect();
      });
    });

    test('connection.ready 重置 _reconnectAttempts，下次退避回到 1s', () {
      FakeAsync().run((FakeAsync async) {
        final factory = FakeChannelFactory();
        final client = RealtimeClient(
          baseUrl: 'http://test',
          getToken: () => 'tok',
          onTokenExpired: () async => false,
          channelFactory: factory.call,
        );

        // 首次连接 + ready（重置计数器为 0）
        client.connect();
        async.flushMicrotasks();
        factory.channels.last.emit(_readyEvent());
        async.flushMicrotasks();
        expect(client.state, ConnectionState.connected);

        // 第一次 drop → 1s 退避
        factory.channels.last.closeServer();
        async.flushMicrotasks();
        async.elapse(const Duration(seconds: 1));
        expect(factory.callCount, 2);
        // 重连后发 ready → 再次重置计数器
        factory.channels.last.emit(_readyEvent());
        async.flushMicrotasks();

        // 第二次 drop → 因为 ready 重置了计数器，应回到 1s（而非 2s）
        factory.channels.last.closeServer();
        async.flushMicrotasks();
        async.elapse(const Duration(milliseconds: 999));
        expect(factory.callCount, 2, reason: '重置后应从 1s 开始，999ms 不应触发');
        async.elapse(const Duration(milliseconds: 2));
        expect(factory.callCount, 3, reason: '重置后 ~1s 应触发重连');

        client.disconnect();
      });
    });
  });

  // ------------------------------------------------------------------
  // Group 10: Channel Close (disconnect / dispose)
  // ------------------------------------------------------------------
  group('Channel Close (disconnect)', () {
    test('disconnect() 取消待处理 reconnect timer，不再创建新 channel', () async {
      final factory = FakeChannelFactory();
      final client = RealtimeClient(
        baseUrl: 'http://test',
        getToken: () => 'tok',
        onTokenExpired: () async => false,
        channelFactory: factory.call,
      );

      client.connect();
      factory.channels.first.emit(_readyEvent());
      await _flush();

      // 触发 drop 以调度 reconnect timer（1s）
      factory.channels.first.closeServer();
      await _flush();
      expect(client.state, ConnectionState.disconnected);

      // 立即 disconnect → _running=false + cancel timer
      client.disconnect();
      await _flush();
      expect(factory.channels.first.isSinkClosed, isTrue);

      // 等待超过 1s backoff，确认没有新 channel 被创建
      await Future<void>.delayed(const Duration(seconds: 1, milliseconds: 300));
      expect(factory.callCount, 1, reason: 'disconnect 后 reconnect timer 应被取消');
    });

    test('disconnect 后不再分发事件（subscription 已 cancel）', () async {
      final events = <EventEnvelope>[];
      final factory = FakeChannelFactory();
      final client = RealtimeClient(
        baseUrl: 'http://test',
        getToken: () => 'tok',
        onTokenExpired: () async => false,
        onEvent: events.add,
        channelFactory: factory.call,
      );

      client.connect();
      factory.channels.first.emit(_readyEvent());
      await _flush();
      events.clear();

      client.disconnect();
      await _flush();

      // 尝试在 disconnect 后 emit — subscription 已 cancel，不应收到
      factory.channels.first.emit(jsonEncode(<String, dynamic>{'type': 'after.disconnect'}));
      await _flush();
      expect(events, isEmpty);
    });
  });

  // ------------------------------------------------------------------
  // Group 11: Connection Failure
  // ------------------------------------------------------------------
  group('Connection Failure', () {
    test('channelFactory 抛异常 → _onDrop → disconnected + 调度 reconnect', () async {
      final states = <ConnectionState>[];
      final factory = FakeChannelFactory();
      factory.throwOnCall = Exception('connection refused');
      final client = RealtimeClient(
        baseUrl: 'http://test',
        getToken: () => 'tok',
        onTokenExpired: () async => false,
        onStateChange: states.add,
        channelFactory: factory.call,
      );
      addTearDown(client.disconnect);

      client.connect();
      await _flush();

      // _open: setState(connecting) → channelFactory 抛异常 → catch → _onDrop
      // _onDrop: _channel 为 null（未赋值），设 disconnected + scheduleReconnect
      expect(client.state, ConnectionState.disconnected);
      expect(factory.uris.length, 1); // factory 被调用了一次（然后抛异常）
      expect(states, contains(ConnectionState.connecting));

      // 等待 backoff 1s，确认重连被调度
      await Future<void>.delayed(const Duration(seconds: 1, milliseconds: 200));
      expect(factory.uris.length, 2, reason: '1s 后应触发重连尝试');
    });
  });

  // ------------------------------------------------------------------
  // Group 12: EventEnvelope 基础解析（保留并强化原有测试）
  // ------------------------------------------------------------------
  group('EventEnvelope 解析', () {
    test('fromJson 解析完整字段', () {
      final e = EventEnvelope.fromJson(<String, dynamic>{
        'type': 'connection.ready',
        'id': 'x',
        'timestamp': 't',
        'payload': <String, dynamic>{'connection_id': 'conn_1'},
      });
      expect(e.type, 'connection.ready');
      expect(e.id, 'x');
      expect(e.timestamp, 't');
      expect(e.payload['connection_id'], 'conn_1');
    });

    test('pong() 和 close() 返回正确 type', () {
      expect(EventEnvelope.pong()['type'], 'connection.pong');
      expect(EventEnvelope.close()['type'], 'connection.close');
    });

    test('ConnectionState.isConnected 仅 connected 为 true', () {
      expect(ConnectionState.connected.isConnected, isTrue);
      for (final s in ConnectionState.values.where((s) => s != ConnectionState.connected)) {
        expect(s.isConnected, isFalse);
      }
    });
  });
}
