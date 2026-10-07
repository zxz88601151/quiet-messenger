// Phase 3A foundation smoke test.
//
// Verifies the app boots, the initial route (/login) renders without crashing,
// and the auth screen shows its expected controls. This is a skeleton check —
// full auth/flow tests belong to later phases.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_client/app/app.dart';

void main() {
  testWidgets('App boots and Login screen renders', (WidgetTester tester) async {
    await tester.pumpWidget(const App());
    await tester.pumpAndSettle();

    // Initial route is /login (see lib/app/router.dart)
    expect(find.text('登录'), findsWidgets);
    expect(find.text('安静、可靠的私人通讯'), findsOneWidget);

    // Login controls present (local-state only at this stage)
    expect(find.byType(TextField), findsAtLeastNWidgets(2));
  });
}
