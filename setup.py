from setuptools import setup, find_packages

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="jupyter_fastapi",
    version="0.0.1",
    author="The Jupyter Team",
    author_email="",
    description="Jupyter Server implemented using FastAPI.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
    ],
    entry_points={
        'console_scripts': [
            'jupyter-fastapi = jupyter_fastapi.app:main'
        ]
    },
    python_requires='>=3.6',
)