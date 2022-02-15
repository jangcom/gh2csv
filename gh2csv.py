"""
gh2csv - GitHub feature exporter

Fetch GitHub feature attributes and export them to a CSV file.

Functions
---------
read_argv(desc='')
    Read in sys.argv.
read_yaml(file, is_echo=False)
    Read in a YAML file encoded in UTF-8.
run_expandvars(s, is_unix_path_delim=True)
    Run os.path.expandvars().
notify_file_gen(f, verb=' generated.')
    Notify that a file has been generated.
warn_to_stdout(notif, border_symb='-', border_num=59,
               is_border=True, is_exit=False)
    Print warning messages to stdout.
interpolate_nums(nums_inp)
    Interpolate a list of numbers.
collect_gh_attrs(yml_arepo, attrs_raw)
    Collect GitHub feature attributes.
collect_gh_attrs_wrapper(yml, arepo)
    collect_gh_attrs() wrapper over active repos
write_to_csv(yml, arepo)
    Export GitHub feature attributes to a CSV file.
run_arepo(yml)
    The main wrapper function
"""
import os
import sys
import re
import copy
from datetime import datetime, timedelta
import argparse
import yaml
import requests
import csv
import schedule


def read_argv(desc=''):
    """Read in sys.argv.

    Parameters
    ----------
    desc : str
        The description of argparse.ArgumentParser (default '')

    Returns
    -------
    argparse.Namespace
        The Namespace object of argparse
    """
    parser = argparse.ArgumentParser(
        description=desc,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('file',
                        help='input file (.yaml)')
    parser.add_argument('--echo',
                        action='store_true',
                        help='display the content of input file')
    parser.add_argument('--nopause',
                        action='store_true',
                        help='do not pause the shell at the end of program')
    return parser.parse_args()


def read_yaml(file,
              is_echo=False):
    """Read in a YAML file encoded in UTF-8.

    Parameters
    ----------
    file : str
        YAML file to be read in
    is_echo : bool
        Dump the YAML content. (default False)

    Returns
    -------
    yaml_loaded : dict
        YAML content
    """
    if not os.path.exists(file):
        print('YAML file not found. Terminating.')
        sys.exit()
    with open(file, encoding='utf-8') as fh:
        yaml_loaded = yaml.load(fh, Loader=yaml.FullLoader)
    if is_echo:
        print('-' * 70)
        print(f'Content of [{file}]')
        print('-' * 70)
        print(yaml.dump(yaml_loaded, sort_keys=False))
    return yaml_loaded


def run_expandvars(s,
                   is_unix_path_delim=True):
    """Run os.path.expandvars().

    Parameters
    ----------
    s : str
        String to be expanded
    is_unix_path_delim : bool
        If True, the MSWin32 path delimiter (\) is converted to
        the Unix-like one (/). (default True)

    Returns
    -------
    s_expanded : str
        The expanded string
    """
    s_expanded = os.path.expandvars(s)
    if is_unix_path_delim:
        s_expanded = re.sub(r'\\', '/', s_expanded)
    return s_expanded


def notify_file_gen(f,
                    verb=' generated.'):
    """Notify that a file has been generated.

    Parameters
    ----------
    f : str
        Filename to be notified.
    verb : str
        Notifying expression (default ' generated.')
    """
    print('[{}]{}'.format(f, verb))


def warn_to_stdout(notif,
                   border_symb='-', border_num=59,
                   is_border=True, is_exit=False):
    """Print warning messages to stdout.

    Parameters
    ----------
    notif : list
        List of strings to be printed
    border_symb : str
        Border symbol (default '-')
    border_num : int
        Number of the border symbols (default 59)
    is_border : bool
        If True, borders will be printed
        before and after the list. (default True)
    is_exit : bool
        If True, the program will be forced to stop. (default False)
    """
    if is_border:
        border = border_symb * border_num
        print(border)
    for line in notif:
        print(line)
    if is_border:
        print(border)
    if is_exit:
        print('Terminating.')
        sys.exit()


def interpolate_nums(nums_inp):
    """Interpolate a list of numbers.

    Parameters
    ----------
    nums_inp : list
        List of strings to be interpolated

    Returns
    -------
    nums_out : list
        List of interpolated integers
    """
    nums_out = []
    for _num in nums_inp:
        if re.search(r'\s*-\s*', _num):  # e.g. 5-10
            beg, end = [int(n) for n in re.split(r'\s*-\s*', _num)]
            end += 1
            nums_out += list(range(beg, end))
        else:
            nums_out.append(int(_num))
    nums_out = list(set(nums_out))  # Duplicate removal
    nums_out = sorted(nums_out)  # Sorting
    return nums_out


def collect_gh_attrs(yml_arepo, attrs_raw):
    """Collect GitHub feature attributes.

    Parameters
    ----------
    yml_arepo : dict
        repo-level YAML-generated dict containing user requests
    attrs_raw : list
        List of dicts of feature attributes

    Returns
    -------
    attrs : list
        List of dicts of filtered feature attributes
    """
    attrs = []
    for attr_raw in attrs_raw:
        # Preprocessing (1/2): Apply the time zone offset.
        for time_attr in ['created_at', 'updated_at', 'closed_at']:
            if attr_raw[time_attr]:
                dt_gh = datetime.strptime(attr_raw[time_attr],
                                          '%Y-%m-%dT%H:%M:%SZ')
                dt_here = dt_gh + timedelta(hours=yml_arepo['io']['out_utc'])
                attr_raw[time_attr] = dt_here
        # Preprocessing (2/2): Collect label names.
        attr_raw['label_names'] = []
        for lab in attr_raw['labels']:  # Iterable: List of dicts
            attr_raw['label_names'].append(lab['name'])
        # The 'labels' list of dicts is destructed and, instead,
        # filled with the list of label names.
        attr_raw['labels'] = ', '.join(attr_raw['label_names'])
        if 'filters' not in yml_arepo:
            attrs.append(attr_raw)
            continue
        #
        # Filters 2 and onward
        # - Set the appending bool, which is True by default, to False.
        #   i.e. Make an issue to be filtered.
        # - Run the issue through the filter and, if it is not filtered,
        #   set the appending bool to True.
        #
        # Appending bool (1/2): Appendable by default
        is_appendable = True
        # Filter 2: Issue numbers
        # - Examine if an issue attribute is contained in
        #   a list of values in YAML
        #   e.g. Issue side: 7
        #        YAML side: [1, 7, 8, 9, 84, 85, 86]
        #        => This issue will not be filtered.
        #   e.g. Issue side: 10
        #        YAML side: [1, 7, 8, 9, 84, 85, 86]
        #        => This issue will be filtered.
        if is_appendable and 'numbers' in yml_arepo['filters']:
            filter_numbers = [str(n) for n in yml_arepo['filters']['numbers']]
            if not re.search('(?i)all', ';'.join(filter_numbers)):
                is_appendable = False
                filter_numbers = interpolate_nums(filter_numbers)
                if attr_raw['number'] in filter_numbers:
                    is_appendable = True
        # Filter 3: Labels or tags
        # - Examine if a stringified issue attribute is contained in
        #   a list of values in YAML
        #   e.g. Issue side: 'bug, enhancement' (from ['bug', 'enhancement'])
        #        YAML side: ['bug', '-invalid', 'documentation']
        #        => This issue will not be filtered.
        #   e.g. Issue side: 'invalid, bug' (from ['invalid', 'bug'])
        #        YAML side: ['bug', '-invalid', 'documentation']
        #        => This issue will be filtered.
        if is_appendable and 'labels' in yml_arepo['filters']:
            filter_labels = yml_arepo['filters']['labels']
            if re.search('(?i)all', ';'.join(filter_labels)):
                is_appendable = True
            else:
                is_appendable = False
            for lab_name in attr_raw['label_names']:
                lab_name_inverted = '-' + lab_name
                if lab_name_inverted in filter_labels:
                    is_appendable = False  # Inversion of 'all => True'
                    break
                if lab_name in filter_labels:
                    is_appendable = True
        # Filter 4: Strings
        # - Examine if any of a given list of values in YAML is contained in
        #   issue attributes.
        #   e.g. YAML side: 'DCPS, -BT'
        #        Issue side: ['(title) DCPS...', '(body) EL...']
        #        => This issue will not be filtered.
        #   e.g. YAML side: 'DCPS, -BT'
        #        Issue side: ['(title) DCPS...', '(body) BT...']
        #        => This issue will be filtered.
        if is_appendable and 'strings' in yml_arepo['filters']:
            filter_strings = yml_arepo['filters']['strings']
            if re.search('(?i)all', ';'.join(filter_strings)):
                is_appendable = True
            else:
                is_appendable = False
            for s in filter_strings:
                is_exclusion = False
                if re.search('^-', s):
                    is_exclusion = True
                    s = s.lstrip('-')
                if (re.search(s, attr_raw['title'])
                        or re.search(s, attr_raw['body'])):
                    if is_exclusion:
                        is_appendable = False  # Inversion of 'all => True'
                        break
                    else:
                        is_appendable = True
        # Appending bool (2/2)
        if is_appendable:
            attrs.append(attr_raw)
    return attrs


def collect_gh_attrs_wrapper(yml, arepo):
    """collect_gh_attrs() wrapper over active repos

    Parameters
    ----------
    yml : dict
        YAML-generated dict containing user requests
    arepo : str
        Active repo
    """
    yml_arepo = yml[arepo]
    headers = {}
    params = {}
    # Token handling for a private repo
    if yml_arepo['is_repo_private']:
        # Token validation
        is_token_err = False
        if 'token' not in yml_arepo:
            is_token_err = True
            notif = [
                '- is_repo_private == True found without the "token" key.',
                '- Create the "token" key and provide it with a valid token.',
            ]
        elif not yml_arepo['token']:
            is_token_err = True
            notif = [
                '- is_repo_private == True found but the "token" is empty.',
                '- Provide the "token" key with a valid token.',
            ]
        if is_token_err:
            notif.insert(0, 'repo: [{}]'.format(arepo))
            warn_to_stdout(notif,
                           is_exit=True)
        # Token designation
        headers['Authorization'] = 'token {}'.format(yml_arepo['token'])
    # Filter 1: State designation via the requests library
    if 'filters' in yml_arepo and 'state' in yml_arepo['filters']:
        params['state'] = yml_arepo['filters']['state']
    # HTTP GET via the requests library
    r0 = requests.get(yml_arepo['url'],
                      headers=headers,
                      params=params)
    if not r0.ok:
        notif = [
            'repo: [{}]'.format(arepo),
            'Access to [{}] failed.'.format(yml_arepo['url']),
            'Check the following items:',
            '- owner',
            '- repo',
            '- token (if is_repo_private == True)',
        ]
        warn_to_stdout(notif,
                       is_exit=True)
        sys.exit()
    # GitHub API v3 restricts the number of attributes per page to 30.
    # For >=30 attributes, r0.header will contain the 'Link' key whose value
    # contains information of the next and last pages of r0.
    # Use the 'Link' key as a hook for page identifications.
    if 'Link' in r0.headers:
        next, last = re.split(r'\s*,\s*', r0.headers['Link'])
        last_url, last_rel = re.split(r'\s*;\s*', last)
        last_url = last_url.strip('<>')
        page_base = re.sub('(?i)(.*page=)[0-9]+', r'\1', last_url)
        last_page_num = int(re.sub('(?i).*page=([0-9]+)', r'\1', last_url))
        r_range = list(range(1, last_page_num + 1))
        for page in r_range:
            page_url = '{}{}'.format(page_base, page)
            r = requests.get(page_url,
                             headers=headers,
                             params=params)
            yml[arepo]['gh_attrs'] += collect_gh_attrs(yml_arepo, r.json())
    else:
        yml[arepo]['gh_attrs'] += collect_gh_attrs(yml_arepo, r0.json())


def write_to_csv(yml, arepo,
                 is_time_series=False):
    """Export GitHub feature attributes to a CSV file.

    Parameters
    ----------
    yml : dict
        YAML-generated dict containing user requests
    arepo : str
        Active repo
    is_time_series : bool
        If True, time series data will be written or appended to a CSV file.
    """
    yml_arepo = yml[arepo]
    out_cols = {
        'attrs': [],  # Keys in the GitHub feature attrs
        'header': [],  # Output file header
    }
    for out_col in yml_arepo['io']['out_cols']:
        spl = re.split(r'\s*;\s*', out_col)
        out_cols['attrs'].append(spl[0])
        out_cols['header'].append(spl[1] if len(spl) >= 2 else spl[0])
    f_mode = 'w'
    last_date = ''
    last_time = ''
    if (is_time_series
            and os.path.exists(yml_arepo['io']['out_fname'])):
        f_mode = 'a'
        idx = {}
        for i, s in enumerate(out_cols['attrs']):
            if re.search('date|time', s):
                idx[s] = i
        with open(yml_arepo['io']['out_fname']) as out_fh:
            last_row = out_fh.readlines()[-1]
            last_row_lst = re.split(r'\s*,\s*', last_row)
            if 'date' in idx:
                last_date = last_row_lst[idx['date']]
            if 'time' in idx:
                last_time = last_row_lst[idx['time']]
    with open(yml_arepo['io']['out_fname'],
              f_mode,
              encoding=yml['run']['io']['out_encoding'],
              newline='') as csv_fh:
        iss_writer = csv.writer(csv_fh, quoting=csv.QUOTE_MINIMAL)
        if f_mode == 'w':
            iss_writer.writerow(out_cols['header'])
        for gh_attr in yml_arepo['gh_attrs']:
            is_date = False
            is_time = False
            is_same_date = False
            is_same_time = False
            row = [gh_attr[out_col] for out_col in out_cols['attrs']]
            if last_date and row[idx['date']]:
                is_date = True
                if last_date == row[idx['date']]:
                    is_same_date = True
            if last_time and row[idx['time']]:
                is_time = True
                if last_time == row[idx['time']]:
                    is_same_time = True
            if is_date and is_time:
                if is_same_date and is_same_time:
                    continue
            elif is_date and not is_time:
                if is_same_date:
                    continue
            elif is_time and not is_date:
                if is_same_time:
                    continue
            iss_writer.writerow(row)
        notify_file_gen(yml_arepo['io']['out_fname'])


def run_arepo(yml):
    """The main wrapper function

    Parameters
    ----------
    yml : dict
        YAML-generated dict containing user requests
    """
    if not yml['run']['active_repos']:
        print("['run']['active_repos'] is empty; terminating.")
        return
    # Iterate over active repos.
    for arepo in yml['run']['active_repos']:
        if arepo not in yml:
            continue
        # Init
        if 'filters' not in yml[arepo]:
            yml[arepo]['filters'] = {}
        yml[arepo]['gh_attrs'] = []
        is_time_series = False
        if 'is_time_series' in yml[arepo] and yml[arepo]['is_time_series']:
            is_time_series = True
        # Inheritance from ['run'] to active repos
        # Precedence: [repo] > ['run']
        for k1 in ['io']:
            if k1 not in yml[arepo]:
                # e.g. yml['el4040_plc']['io'] <-copy- yml['run']['io']
                yml[arepo][k1] = copy.deepcopy(yml['run'][k1])
            # The contents of first subkeys of k1 can all be overridden.
            # e.g. ['run']['io']['out_path']
            if isinstance(yml['run'][k1], dict):
                for k2 in yml['run'][k1]:
                    if k2 not in yml[arepo][k1]:
                        # e.g. yml['el4040_plc']['io']['out_path']
                        #      <-copy- yml['run']['io']['out_path']
                        yml[arepo][k1][k2] = copy.deepcopy(yml['run'][k1][k2])
        # Preprocessing on top of the inheritance
        out_path = run_expandvars(yml[arepo]['io']['out_path'])
        if not os.path.exists(out_path):
            os.makedirs(out_path)
            notify_file_gen(out_path)
        comps = []
        for comp in yml[arepo]['io']['out_bname_comps']:  # e.g. repo, feature
            comps.append(yml[arepo][comp])
        out_bname = '_'.join(comps)
        yml[arepo]['io']['out_fname'] = '{}/{}.csv'.format(out_path, out_bname)
        url_base = 'https://api.github.com/repos'
        yml[arepo]['url'] = '{}/{}/{}/{}'.format(url_base,
                                                 yml[arepo]['owner'],
                                                 yml[arepo]['repo'],
                                                 yml[arepo]['feature'])
        # Fetch GitHub feature attributes and assign them to yml[arepo].
        collect_gh_attrs_wrapper(yml, arepo)
        # Generate, if requested, time series data.
        if is_time_series:
            # Run the arepo again with the 'state' = 'closed'
            # to obtain the numbers of closed issues.
            yml[arepo]['filters']['state'] = 'closed'
            collect_gh_attrs_wrapper(yml, arepo)
            # Count the number of issues for time series data.
            for state in ['all', 'open', 'closed']:
                k = 'num_iss_{}'.format(state)
                yml[arepo][k] = 0
            for gh_attr in yml[arepo]['gh_attrs']:
                yml[arepo]['num_iss_all'] += 1
                if re.search('open', gh_attr['state']):
                    yml[arepo]['num_iss_open'] += 1
                if re.search('closed', gh_attr['state']):
                    yml[arepo]['num_iss_closed'] += 1
            # Overwrite yml[arepo]['gh_attrs'], which contains dictionaries of
            # GitHub attributes, by a dictionary of values obtained from within
            # this program, to make this arepo fit with write_to_csv().
            _today = datetime.today()
            yml[arepo]['gh_attrs'] = [{
                'date': _today.strftime('%Y/%m/%d'),
                'time': _today.strftime('%H:%M:%S'),
                'num_iss_all': yml[arepo]['num_iss_all'],
                'num_iss_open': yml[arepo]['num_iss_open'],
                'num_iss_closed': yml[arepo]['num_iss_closed'],
            }]
        # Write the fetched GitHub attributes to a CSV file.
        write_to_csv(yml, arepo,
                     is_time_series=is_time_series)


if __name__ == '__main__':
    argv = read_argv()
    the_yml = read_yaml(argv.file, is_echo=argv.echo)
    if 'schedule' in the_yml['run'] and the_yml['run']['schedule']['toggle']:
        print('[{}] Running in scheduled mode...'.format(datetime.now()))
        obj = getattr(schedule.every(), the_yml['run']['schedule']['every'])
        if 'at' in the_yml['run']['schedule']:
            obj = getattr(obj, 'at')(the_yml['run']['schedule']['at'])
        obj.do(run_arepo, the_yml)
        while True:
            schedule.run_pending()
    else:
        run_arepo(the_yml)
    if not argv.nopause:
        input('Press enter to exit...')
