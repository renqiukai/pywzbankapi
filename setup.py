from setuptools import setup, find_packages

version = "1.0.0"
setup(
    name="pywzbankapi",
    version=version,
    keywords=[
        "wzbank",
    ],
    description="",
    long_description="",
    license="MIT Licence",
    url="https://github.com/renqiukai/pywzbankapi",
    author="Renqiukai",
    author_email="renqiukai@qq.com",
    packages=find_packages(),
    include_package_data=True,
    platforms="any",
    install_requires=["requests", "loguru"],
)
