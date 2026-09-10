import 'package:flutter/animation.dart';

abstract final class VPushMotion {
  static const standard = Duration(milliseconds: 160);
  static const loginCard = Duration(milliseconds: 240);
  static const bottomNavigation = Duration(milliseconds: 180);
  static const bottomFeedback = Duration(milliseconds: 220);
  static const lightbox = Duration(milliseconds: 250);
  static const toastIn = Duration(milliseconds: 180);
  static const toastOut = Duration(milliseconds: 300);

  static const standardCurve = Cubic(0.25, 0.1, 0.25, 1);
  static const enterCurve = Cubic(0.22, 1, 0.36, 1);
  static const formCurve = Cubic(0.16, 1, 0.3, 1);
}
