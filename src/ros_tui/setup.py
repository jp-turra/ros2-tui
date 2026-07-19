from setuptools import find_packages, setup

package_name = 'ros_tui'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    package_data={'': ['py.typed']},
    install_requires=[
        'setuptools',
        'textual==8.2.8',
    ],
    zip_safe=True,
    maintainer='João Turra',
    maintainer_email='joao.t06@hotmail.com',
    description='A ROS 2 TUI app to update parameters, call services, monitor topics and send actions.',
    license='GPL v3',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'ros_tui = ros_tui.app:main',
        ],
    },
)
