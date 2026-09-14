#!/usr/bin/env bash
# Linux Bash initializer; all paths are relative to this script, not $PWD.
set -Eeuo pipefail
export PYTHONUTF8=1
trap 'printf "\n初始化失败（第 %s 行）。请修复上述错误后重试。\n" "$LINENO" >&2' ERR
fail() { printf '错误：%s\n' "$*" >&2; exit 1; }
[[ ${OSTYPE:-} == linux* ]] || fail '此脚本仅支持 Linux Bash。'
script_path=${BASH_SOURCE[0]}
[[ $script_path == */* ]] || script_path=./$script_path
script_dir=$(cd -- "${script_path%/*}" && pwd -P)
binary="$script_dir/hugemark-linux-amd64"
venv_dir="$script_dir/.venv"
venv_python="$venv_dir/bin/python"
requirements="$script_dir/.hugemark-requirements.txt"
[[ -f "$binary" ]] || fail "同目录缺少 hugemark-linux-amd64：$binary"
[[ -x "$binary" ]] || chmod u+x -- "$binary"
version=$("$binary" --version) || fail '二进制无法运行；请确认使用 Linux amd64 发行包和兼容的系统。'
[[ $version == 'hugemark '* ]] || fail '二进制版本输出不属于 Hugemark。'
printf '二进制：%s\n版本：%s\n' "$binary" "$version"
for resource in requirements-gui.txt initialize_environment.py gui.py desktop.py assets/desktop.qss assets/fonts/NotoSansCJKsc-Regular.otf; do
    [[ -f "$script_dir/$resource" ]] || fail "发行包不完整，缺少 $resource"
done
uv_path=$(command -v uv || true)
usable_python() { "$1" -c 'import sys,struct;sys.exit(not (sys.version_info >= (3,12) and struct.calcsize("P")==8))' >/dev/null 2>&1; }
base_python=''
if [[ -e "$venv_dir" ]]; then
    [[ -f "$venv_dir/pyvenv.cfg" ]] && usable_python "$venv_python" || fail '.venv 已存在但不可用（需要 64 位 Python 3.12+）；请备份或移走后重试。'
    base_python=$venv_python
else
    for candidate in python3 python python3.14 python3.13 python3.12; do
        resolved=$(command -v "$candidate" || true)
        if [[ -n $resolved ]] && usable_python "$resolved"; then base_python=$resolved; break; fi
    done
    if [[ -z $base_python && -n $uv_path ]]; then
        resolved=$("$uv_path" python find --no-python-downloads '>=3.12' 2>/dev/null || true)
        if [[ -n $resolved ]] && usable_python "$resolved"; then base_python=$resolved; fi
    fi
    [[ -n $base_python ]] || fail '找不到可用的 64 位 Python 3.12+。请先安装 Python；脚本不会自动下载解释器。'
    if [[ -n $uv_path ]]; then
        "$uv_path" venv --no-python-downloads --python "$base_python" "$venv_dir"
    else
        "$base_python" -m venv "$venv_dir"
    fi
fi
usable_python "$venv_python" || fail '虚拟环境 Python 无法运行。'
"$binary" requirements > "$requirements"
[[ -s "$requirements" ]] || fail '二进制未输出依赖清单。'
printf '\n安装全部依赖（每次执行均重新安装）…\n'
if [[ -n $uv_path ]]; then
    "$uv_path" pip install --python "$venv_python" --reinstall -r "$requirements" -r "$script_dir/requirements-gui.txt"
    "$uv_path" pip check --python "$venv_python"
else
    "$venv_python" -m ensurepip --upgrade
    "$venv_python" -m pip install --force-reinstall -r "$requirements" -r "$script_dir/requirements-gui.txt"
    "$venv_python" -m pip check
fi
"$venv_python" "$script_dir/initialize_environment.py" "$binary"
printf '\n初始化成功\n二进制：%s\nPython：%s\n虚拟环境：%s\n安装工具：%s\n依赖：已重新安装并通过检查\n启动 GUI：\n' "$binary" "$venv_python" "$venv_dir" "${uv_path:-python -m pip}"
printf '  %q %q\n' "$venv_python" "$script_dir/gui.py"
if [[ -t 0 ]]; then
    printf '\n按任意键退出…'
    IFS= read -r -s -n 1
    printf '\n'
else
    printf '\n非交互输入，跳过按键等待。\n'
fi
