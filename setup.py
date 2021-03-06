import os
from os import path
from setuptools import setup
from distutils import sysconfig

base_path = '/opt/newrelic_plugin_agent'
data_files = dict()
data_files[base_path] = ['README.md']

# Check to see if the previous version was installed and clean up
# installed-files.txt
prune = ['/', 'var/', 'var/run/', 'var/log/']
python_lib_dir = sysconfig.get_python_lib()
fixed = False
for dir_path, dir_names, file_names in os.walk(python_lib_dir):
    for dir_name in dir_names:
        if dir_name[:21] == 'newrelic_plugin_agent' and \
                        dir_name[-8:] == 'egg-info':
            filename = '%s/%s/installed-files.txt' % (python_lib_dir, dir_name)
            with open(filename, 'r') as handle:
                output = []
                for line in handle:
                    safe = True
                    for dir_path in prune:
                        if line[-(len(dir_path) + 1):].strip() == dir_path:
                            safe = False
                            fixed = True
                            break
                    if safe:
                        output.append(line.strip())
            with open(filename, 'w') as handle:
                handle.write('\n'.join(output))
            break
    break
if fixed:
    print 'Fixed a serious uninstallation problem in previous version'

# etc dir
for dir_path, dir_names, file_names in os.walk('etc'):
    install_path = '%s/%s' % (base_path, dir_path)
    if len(file_names) > 0 and install_path not in data_files:
        data_files[install_path] = list()
    for file_name in file_names:
        data_files[install_path].append('%s/%s' % (dir_path, file_name))

# var dir
for dir_path, dir_names, file_names in os.walk('var'):
    install_path = '/%s' % dir_path
    if len(file_names) > 0 and install_path not in data_files:
        data_files[install_path] = list()
    for file_name in file_names:
        data_files[install_path].append('%s/%s' % (dir_path, file_name))

with open('MANIFEST.in', 'w') as handle:
    for path in data_files:
        for filename in data_files[path]:
            handle.write('include %s\n' % filename)

console_scripts = ['newrelic_plugin_agent=newrelic_plugin_agent.agent:main']
install_requires = ['clihelper>=1.7.0', 'requests']
tests_require = []
extras_require = {'mongodb': ['pymongo'],
                  'pgbouncer': ['psycopg2'],
                  'postgresql': ['psycopg2']}

setup(name='newrelic_plugin_agent',
      version='1.0.13',
      description='Python based agent for collecting metrics for NewRelic',
      url='https://github.com/MeetMe/newrelic_plugin_agent',
      packages=['newrelic_plugin_agent', 'newrelic_plugin_agent.plugins'],
      author='Gavin M. Roy',
      author_email='gmr@meetme.com',
      license='BSD',
      entry_points={'console_scripts': console_scripts},
      data_files=[(key, data_files[key]) for key in data_files.keys()],
      install_requires=install_requires,
      extras_require=extras_require,
      tests_require=tests_require,
      classifiers=[
          'Development Status :: 4 - Beta',
          'Intended Audience :: System Administrators',
          'License :: OSI Approved :: BSD License',
          'Operating System :: POSIX',
          'Operating System :: POSIX :: Linux',
          'Programming Language :: Python :: 2',
          'Programming Language :: Python :: 2.6',
          'Programming Language :: Python :: 2.7',
          'Programming Language :: Python :: 2 :: Only',
          'Topic :: System :: Monitoring'])
