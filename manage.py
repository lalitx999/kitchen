#!/usr/bin/env python
"""Django command-line utility. Defaults to local settings; production sets DJANGO_SETTINGS_MODULE."""
import os
import sys


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
