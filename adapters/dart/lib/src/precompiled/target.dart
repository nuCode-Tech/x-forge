import 'dart:io';

String detectHostTargetTriple() {
  final arch = _detectArch();
  switch (Platform.operatingSystem) {
    case 'macos':
      return arch == 'aarch64'
          ? 'aarch64-apple-darwin'
          : 'x86_64-apple-darwin';
    case 'linux':
      return arch == 'aarch64'
          ? 'aarch64-unknown-linux-gnu'
          : 'x86_64-unknown-linux-gnu';
    case 'windows':
      return arch == 'aarch64'
          ? 'aarch64-pc-windows-msvc'
          : 'x86_64-pc-windows-msvc';
    case 'android':
      return switch (arch) {
        'aarch64' => 'aarch64-linux-android',
        'arm' => 'armv7-linux-androideabi',
        'x86' => 'i686-linux-android',
        _ => 'x86_64-linux-android',
      };
    case 'ios':
      return arch == 'aarch64'
          ? 'aarch64-apple-ios'
          : 'x86_64-apple-ios';
    default:
      return 'x86_64-unknown-linux-gnu';
  }
}

String _detectArch() {
  final env = Platform.environment;
  final raw = [
    env['PROCESSOR_ARCHITECTURE'],
    env['PROCESSOR_IDENTIFIER'],
    env['HOSTTYPE'],
    env['MACHTYPE'],
    Platform.version,
    Platform.operatingSystemVersion,
  ].whereType<String>().join(' ').toLowerCase();

  if (raw.contains('aarch64') || raw.contains('arm64')) {
    return 'aarch64';
  }
  if (raw.contains('x86_64') || raw.contains('amd64') || raw.contains('x64')) {
    return 'x86_64';
  }
  if (raw.contains('i686') || raw.contains('i386') || raw.contains('x86')) {
    return 'x86';
  }
  if (raw.contains('arm')) {
    return 'arm';
  }
  return 'x86_64';
}
