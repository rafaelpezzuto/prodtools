
import sys

from app_modules.generics import system
from app_modules.__init__ import appcaller
from app_modules.__init__ import BIN_XML_PATH


def execute(parameters):
    appcaller.execute(
        [system.format_command(
            'python {}/run_app.py'.format(BIN_XML_PATH), parameters)])


def requirements_checker():
    required = []
    try:
        import PIL
    except:
        required.append('PIL')
    try:
        import packtools
    except:
        required.append('packtools')
    return required


def check_requirements():
    reqs = requirements_checker()
    if len(reqs) > 0:
        appcaller.install_virtualenv()
        appcaller.install_requirements()


def main(parameters):
    argv = parameters[1:]

    if parameters[1].endswith('xml_package_maker.py'):
        check_requirements()
        from app_modules.app import xpm
        xpm.call_make_packages(argv, '1.1')
    elif parameters[1].endswith('xml_converter.py'):
        check_requirements()
        from app_modules.app import xc
        xc.call_converter(argv, '1.1')
    elif parameters[1] == 'install':
        appcaller.install_virtualenv(True)
        appcaller.install_requirements()
    else:
        print('unknown command')
        print(parameters)
        print('do nothing')


if __name__ == '__main__':
    main(sys.argv)
