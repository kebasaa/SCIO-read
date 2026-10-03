"""Hash local downloaded tooling without exporting build paths or app constants."""
import argparse
import subprocess
from pathlib import Path
import _bootstrap
from scio_offline import research as r


def revision(path):
    result = subprocess.run(['git','-C',str(path),'rev-parse','HEAD'],
                            capture_output=True,text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    private = r.DEV/'private'
    files = []
    for path in sorted((private/'native_debs').glob('*.deb')):
        files.append({'file':path.name,'sha256':r.sha(path.read_bytes()),'bytes':path.stat().st_size})
    tool = private/'blutter'
    report = {'blutter_source':'https://github.com/worawit/blutter',
              'blutter_commit':revision(tool),
              'dart_source':'https://github.com/dart-lang/sdk',
              'dart_requested_tag':'3.7.2','dart_commit':revision(tool/'dartsdk/v3.7.2'),
              'compiler':'Existing Ubuntu GCC 13.3 via WSL; MSVC 18.9 confirmed as fallback',
              'compiler_installed':False,'system_packages_installed':False,
              'dependency_archives':files,
              'local_tool_changes':{'blutter.py':r.sha((tool/'blutter.py').read_bytes()),
                                    'dartvm_fetch_build.py':r.sha((tool/'dartvm_fetch_build.py').read_bytes()),
                                    'blutter/src/DartDumper.cpp':r.sha((tool/'blutter/src/DartDumper.cpp').read_bytes()),
                                    'blutter/src/CodeAnalyzer.cpp':r.sha((tool/'blutter/src/CodeAnalyzer.cpp').read_bytes())},
              'change_description':'Ninja limited to two jobs; library-ID filenames; include separate nativeLib and its synthetic top class, with anonymous function headers that do not dereference missing Dart Function metadata.',
              'limits':'Source/dependency provenance, not a claim that build or analysis completed. All third-party binaries, source and analysis outputs stay ignored under dev/private.'}
    r.write_new(a.output,report)
    print('Recorded toolchain provenance:',len(files),'dependency archives')


if __name__ == '__main__':
    main()
