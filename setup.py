from setuptools import find_packages, setup

setup(
    name="dulwich-benchmarks",
    version="0.1.0",
    description="Performance benchmarks for Dulwich",
    packages=find_packages(),
    install_requires=[
        "asv>=0.6.0",
        "dulwich",
    ],
    python_requires=">=3.9",
)
