import os, glob, yaml, re, sys
from main import run_for_user

ROOT = os.path.dirname(os.path.dirname(__file__))
def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

if __name__ == "__main__":
    defaults = load_yaml(os.path.join(ROOT, "src", "defaults.yaml"))
    user_files = sorted(glob.glob(os.path.join(ROOT, "configs", "users", "*.yaml")))
    if not user_files:
        print("[WARN] 没有找到用户配置文件")
        sys.exit(0)

    ok = []
    for uf in user_files:
        try:
            user_cfg = load_yaml(uf)
            fn = run_for_user(user_cfg, defaults)
            ok.append(fn)
        except Exception as e:
            print(f"[SKIP] {os.path.basename(uf)} -> {e}")
    print("[DONE] generated feeds:", ok)
