## NAME

gh2csv - GitHub feature exporter

## SYNOPSIS

    gh2csv.py [-h] [--echo] [--nopause] file

## DESCRIPTION

    Fetch GitHub feature attributes and export them to a CSV file.

## OPTIONS

    file
        input file (.yaml)

    -h, --help
        help message

    --echo
        display the content of input file (default: False)

    --nopause
        do not pause the shell at the end of program (default: False)

## INPUT FILE SYNTAX

    Refer to the enclosed file "sample.yaml".

## EXAMPLES

    python gh2csv.py sample.yaml

## DEPENDENCIES

- PyYAML v5.3.1
- Requests v2.26.0
- schedule v1.1.0

## AUTHOR

Jaewoong Jang \<jangj@korea.ac.kr\>

## COPYRIGHT

Copyright (c) 2021-2022 Jaewoong Jang

## LICENSE

This software is available under the MIT license;
the license information is found in 'LICENSE'.
