#!/usr/bin/env python3
"""`flutter create` ilə yaradılmış android/ və ios/ qovluqlarına YALNIZ İNKİŞAF üçün lazım olan
konfiqurasiyanı əlavə edir (təkrar işlətmək təhlükəsizdir):

  Android: INTERNET icazəsi (main) + debug manifestdə düz HTTP (cleartext) icazəsi.
  iOS    : Info.plist-ə lokal şəbəkə HTTP istisnası (NSAllowsLocalNetworking) və lokal şəbəkə izahı.

PRODUCTION üçün: API HTTPS olmalıdır. iOS Info.plist-dəki NSAppTransportSecurity blokunu silin;
Android-də cleartext yalnız debug manifestdədir, release build-ə düşmür.
İstifadə (mobile/ qovluğundan):  python3 tool/apply_dev_platform_config.py
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def patch_android() -> None:
    main = ROOT / "android/app/src/main/AndroidManifest.xml"
    debug = ROOT / "android/app/src/debug/AndroidManifest.xml"
    if not main.exists():
        sys.exit("android/ tapılmadı. Əvvəlcə: flutter create --platforms=android,ios --org az.bakuflow --project-name bakuflow_mobile .")
    text = main.read_text(encoding="utf-8")
    if "android.permission.INTERNET" not in text:
        text = re.sub(r"(<manifest[^>]*>)", r'\1\n    <uses-permission android:name="android.permission.INTERNET"/>', text, count=1)
        main.write_text(text, encoding="utf-8")
        print("Android main manifest: INTERNET icazəsi əlavə olundu")
    debug.parent.mkdir(parents=True, exist_ok=True)
    if debug.exists():
        d = debug.read_text(encoding="utf-8")
    else:
        d = '<manifest xmlns:android="http://schemas.android.com/apk/res/android">\n</manifest>\n'
    if "usesCleartextTraffic" not in d:
        d = d.replace("</manifest>", '    <application android:usesCleartextTraffic="true"/>\n</manifest>')
        debug.write_text(d, encoding="utf-8")
        print("Android debug manifest: usesCleartextTraffic=true (yalnız debug)")
    if "android.permission.INTERNET" not in d:
        d = re.sub(r"(<manifest[^>]*>)", r'\1\n    <uses-permission android:name="android.permission.INTERNET"/>', d, count=1)
        debug.write_text(d, encoding="utf-8")


def patch_ios() -> None:
    plist = ROOT / "ios/Runner/Info.plist"
    if not plist.exists():
        sys.exit("ios/Runner/Info.plist tapılmadı (flutter create işlədilməyib?)")
    t = plist.read_text(encoding="utf-8")
    add = ""
    if "NSAppTransportSecurity" not in t:
        add += (
            "\t<key>NSAppTransportSecurity</key>\n\t<dict>\n\t\t<key>NSAllowsLocalNetworking</key>\n\t\t<true/>\n\t</dict>\n"
        )
    if "NSLocalNetworkUsageDescription" not in t:
        add += (
            "\t<key>NSLocalNetworkUsageDescription</key>\n"
            "\t<string>Lokal inkişaf serverinə (BakuFlow backend) qoşulmaq üçün lazımdır.</string>\n"
        )
    if add:
        t = t.replace("</dict>\n</plist>", add + "</dict>\n</plist>")
        plist.write_text(t, encoding="utf-8")
        print("iOS Info.plist: lokal şəbəkə HTTP istisnası əlavə olundu (yalnız inkişaf üçün)")


if __name__ == "__main__":
    patch_android()
    patch_ios()
    print("Hazırdır.")
