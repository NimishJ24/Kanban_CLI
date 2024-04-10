from setuptools import setup
import os

# with open(os.path.join(os.getcwd(), 'VERSION')) as version_file:
#     version = version_file.read().strip()

# with open("README.md", "r") as fh:
#     long_description = fh.read()

setup(
    name="kanbancli",
    version='0.0.0',
    description="Simple CLI-based Kanban board",
    py_modules=['kanbancli'],
    install_requires=[
        'Click',
        'click-default-group',
        'pyyaml',
        'rich'
    ],
    entry_points='''
        [console_scripts]
        kanbancli=kanbancli:kanbancli
        alexa=kanbancli:kanbancli
    ''',
)