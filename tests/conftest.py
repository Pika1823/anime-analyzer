import sys
from pathlib import Path

# テストから scripts/ 配下のモジュールをインポートできるようにする
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
