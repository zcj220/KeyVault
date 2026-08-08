#!/bin/bash
# 生成带自定义图标的 KeyVault.app（macOS）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/KeyVault.app"
ICON="$ROOT/assets/AppIcon.icns"

if [[ ! -f "$ICON" ]]; then
  echo "缺少图标: $ICON"
  exit 1
fi

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>
  <string>KeyVault</string>
  <key>CFBundleDisplayName</key>
  <string>KeyVault</string>
  <key>CFBundleIdentifier</key>
  <string>com.xinzaoai.keyvault.launcher</string>
  <key>CFBundleVersion</key>
  <string>1.0</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleExecutable</key>
  <string>KeyVault</string>
  <key>CFBundleIconFile</key>
  <string>AppIcon</string>
  <key>LSMinimumSystemVersion</key>
  <string>12.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST

cp "$ICON" "$APP/Contents/Resources/AppIcon.icns"

cat > "$APP/Contents/MacOS/KeyVault" <<'EXEC'
#!/bin/bash
# KeyVault.app 在项目根目录时：../../../../ = 仓库根
APP_BIN_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$APP_BIN_DIR/../../../.." && pwd)"
if [[ -x "$PROJECT_ROOT/scripts/launch-ui.sh" ]]; then
  exec "$PROJECT_ROOT/scripts/launch-ui.sh"
fi
# 桌面拷贝的 App：读内嵌标记文件
MARKER="$(cd "$APP_BIN_DIR/../Resources" && pwd)/project-root"
if [[ -f "$MARKER" ]]; then
  PROJECT_ROOT="$(cat "$MARKER")"
  if [[ -x "$PROJECT_ROOT/scripts/launch-ui.sh" ]]; then
    exec "$PROJECT_ROOT/scripts/launch-ui.sh"
  fi
fi
osascript -e 'display dialog "找不到 KeyVault 项目。请把 KeyVault.app 放在仓库根目录，或重新运行 scripts/build-macos-app.sh。" buttons {"好"} default button 1 with title "KeyVault"'
exit 1
EXEC
chmod +x "$APP/Contents/MacOS/KeyVault"

# 写入项目根路径，方便桌面拷贝也能启动
printf '%s\n' "$ROOT" > "$APP/Contents/Resources/project-root"

# 桌面拷贝（带图标，好认）
DEST_DESKTOP="$HOME/Desktop/KeyVault.app"
rm -rf "$DEST_DESKTOP"
# 去掉旧的 .command 替身，避免混淆
rm -f "$HOME/Desktop/KeyVault启动.command"
cp -R "$APP" "$DEST_DESKTOP"
printf '%s\n' "$ROOT" > "$DEST_DESKTOP/Contents/Resources/project-root"

touch "$APP" "$DEST_DESKTOP" || true

echo "已生成: $APP"
echo "桌面:   $DEST_DESKTOP"
