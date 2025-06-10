load("@rules_python//python:pip.bzl", "compile_pip_requirements")
load("@rules_python//python:py_binary.bzl", "py_binary")

compile_pip_requirements(
    name = "requirements",
    src = "requirements.in",
    requirements_txt = "requirements_lock.txt",
)

py_binary(
    name = "main",
    srcs = [
        "data.py",
        "main.py",
    ],
    deps = [
        "@pypi//beautifulsoup4",
        "@pypi//requests",
    ],
)
