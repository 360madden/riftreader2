"""Fail unless the validation interpreter provides the pinned Lua 5.1 runtime."""
import lupa
from lupa.lua51 import LuaRuntime

if lupa.__version__ != "2.8" or LuaRuntime().eval("_VERSION") != "Lua 5.1":
    raise SystemExit("Lua 5.1 test runtime missing or wrong lupa version.")
