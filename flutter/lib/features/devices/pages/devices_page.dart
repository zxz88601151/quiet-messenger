/// Devices — real server data (UI Functional Recovery).
///
/// V1.1 MUST HAVE #4: shows device type/name/online/current/last active +
/// remove. Reads from GET /devices via [DeviceRepository]. Remove calls
/// DELETE /devices/{id} with confirmation. No mock data.
///
/// States: Loading / Success / Empty / Error + Retry.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../app/theme/colors.dart';
import '../../../app/theme/typography.dart';
import '../models/device.dart';
import '../repositories/device_repository.dart';

class DevicesPage extends StatefulWidget {
  const DevicesPage({super.key});

  @override
  State<DevicesPage> createState() => _DevicesPageState();
}

class _DevicesPageState extends State<DevicesPage> {
  bool _loading = true;
  String? _error;
  List<Device> _devices = const [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final repo = context.read<DeviceRepository>();
      final list = await repo.list();
      if (mounted) {
        setState(() {
          _devices = list;
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString().split('\n').first;
          _loading = false;
        });
      }
    }
  }

  Future<void> _remove(Device device) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('移除设备'),
        content: Text('确定要移除「${device.displayName}」吗？该设备将立即失去登录权限。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('取消'),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: AppColors.error),
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('移除'),
          ),
        ],
      ),
    );

    if (confirmed != true) return;

    try {
      final repo = context.read<DeviceRepository>();
      await repo.revoke(device.id);
      if (mounted) {
        setState(() {
          _devices = _devices.where((d) => d.id != device.id).toList();
        });
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('已移除 ${device.displayName}')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('移除失败: ${e.toString().split('\n').first}'),
            backgroundColor: AppColors.error,
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('登录设备'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loading ? null : _load,
            tooltip: '刷新',
          ),
        ],
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, size: 48, color: AppColors.error),
            const SizedBox(height: 12),
            Text(_error!, style: AppTypography.caption),
            const SizedBox(height: 16),
            ElevatedButton(onPressed: _load, child: const Text('重试')),
          ],
        ),
      );
    }
    if (_devices.isEmpty) {
      return const Center(
        child: Text('暂无登录设备', style: AppTypography.caption),
      );
    }
    return ListView.separated(
      itemCount: _devices.length,
      separatorBuilder: (_, __) => const Divider(height: 1),
      itemBuilder: (_, i) => _DeviceTile(device: _devices[i], onRemove: _remove),
    );
  }
}

class _DeviceTile extends StatelessWidget {
  const _DeviceTile({required this.device, required this.onRemove});

  final Device device;
  final void Function(Device) onRemove;

  IconData get _icon {
    switch (device.deviceType.toLowerCase()) {
      case 'ios':
      case 'iphone':
        return Icons.phone_iphone;
      case 'android':
        return Icons.phone_android;
      case 'windows':
      case 'desktop':
        return Icons.desktop_windows;
      case 'macos':
      case 'mac':
        return Icons.laptop_mac;
      case 'linux':
        return Icons.laptop;
      default:
        return Icons.devices;
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: Icon(_icon, color: device.isCurrent ? AppColors.primary : AppColors.text2),
      title: Text(device.displayName, style: AppTypography.subtitle),
      subtitle: Text(
        '${device.deviceType}'
        '${device.isCurrent ? " · 当前设备" : ""}'
        '${device.isRevoked ? " · 已撤销" : ""}',
        style: AppTypography.caption,
      ),
      trailing: device.isCurrent || device.isRevoked
          ? null
          : TextButton(
              onPressed: () => onRemove(device),
              child: const Text('移除', style: TextStyle(color: AppColors.error)),
            ),
    );
  }
}
