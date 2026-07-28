"""PyInstaller exe로 패키징했을 때와 python 스크립트로 직접 실행했을 때
모두 올바르게 동작하도록 경로를 결정하는 공용 헬퍼.

- app_dir(): 쓰기 가능한 사용자 데이터(이력 json, read 폴더) 기준 경로.
  exe 파일이 실제로 놓인 위치를 기준으로 잡아야 한다. PyInstaller onefile은
  실행할 때마다 임시 폴더에 압축을 풀고 종료하면 지워버리기 때문에, __file__
  기준으로 잡으면 데이터가 매번 사라진다.
- bundle_dir(): 읽기 전용 리소스(엑셀 템플릿) 기준 경로. exe 안에 포함된
  파일은 PyInstaller가 풀어놓는 임시 번들 경로(sys._MEIPASS)에서 찾아야 한다.
"""

import os
import sys


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def bundle_dir():
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", app_dir())
    return os.path.dirname(os.path.abspath(__file__))
