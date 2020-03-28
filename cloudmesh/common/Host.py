import os
import subprocess
from multiprocessing import Pool
from sys import platform

from cloudmesh.common.parameter import Parameter
from cloudmesh.common.util import path_expand
import time
from pprint import pprint
from cloudmesh.common.Shell import Shell
import textwrap
from cloudmesh.common.DateTime import DateTime

class Host(object):

    @staticmethod
    def config(hosts=None,
               ips=None,
               username=None,
               key="~/.ssh/id_rsa.pub"):

        if type(hosts) != list:
            _hosts = Parameter.expand(hosts)
        if type(ips) != list:
            _ips = Parameter.expand(ips)
        if len(_ips) != len(_hosts):
            raise ValueError("Number of hosts and ips mismatch")

        result = ""
        for i in range(0,len(_hosts)):

            host = _hosts[i]
            ip = _ips[i]

            user = f"user {username}"
            data = textwrap.dedent(f"""
            Host {host}
                StrictHostKeyChecking no
                LogLevel ERROR
                UserKnownHostsFile /dev/null
                Hostname {ip}
                IdentityFile {key}
            """)
            if username:
                data += (f"    {user}\n")

            result += data
        return result


    @staticmethod
    def _run(args):
        """

        An internal command that executes as part of a process map a given
        command. args is a dict and must include

        * command
        * shell

        It returns a dict of the form

        * command
        * stdout
        & stderr
        * returncode
        * success

        :param args: command dict
        :return:
        """
        command = args.get("command")
        shell = args.get("shell")

        result = subprocess.run(command,
                                capture_output=True,
                                shell=shell)
        now = DateTime.now()
        result.stdout = result.stdout.decode("utf-8").strip()

        if result.stderr == b'':
            result.stderr = None
        data = {
            'host': args.get("host"),
            'command': args.get("command"),
            'stdout': result.stdout,
            'stderr': result.stderr,
            'returncode': result.returncode,
            'success': result.returncode == 0,
            'date': now
        }
        return data

    @staticmethod
    def run(hosts=None,
            command=None,
            processors=3,
            shell=False,
            **kwargs):
        """
        Executes the command on all hosts. The key values
        specified in **kwargs will be replaced prior to the
        execution. Furthermore, {host} will be replaced with the
        specific hostname.

        :param hosts: The hosts given in parameter notation
                      Example: red[01-10]
        :param command: The command to be executed for each host
                        Example: ssh {host} uname
        :param username: Specify the username on the host
        :param processors: The number of parallel processes used
        :param shell: Set to Tue if the current context of the shell is
                      to be used. It is by default True
        :param kwargs: The key value pairs to be replaced in the command
        :return:
        """

        if type(hosts) != list:
            hosts = Parameter.expand(hosts)

        args = [{'command': [c.format(host=host, **kwargs) for c in command],
                 'shell': shell,
                 'host': host,
                 } for host in hosts]

        if "executor" not in args:
            executor = Host._run

        with Pool(processors) as p:
            res = p.map(executor, args)
            p.close()
            p.join()
        return res

    @staticmethod
    def ssh(hosts=None,
            command=None,
            username=None,
            key="~/.ssh/id_rsa.pub",
            processors=3,
            dryrun=False,  # notused
            executor=None,
            verbose=False):  # not used
        #
        # BUG: this code has a bug and does not deal with different
        #  usernames on the host to be checked.
        #
        """

        :param command: the command to be executed
        :param hosts: a list of hosts to be checked
        :param username: the usernames for the hosts
        :param key: the key for logging in
        :param processors: the number of parallel checks
        :return: list of dicts representing the ping result
        """

        if type(hosts) != list:
            hosts = Parameter.expand(hosts)

        key = path_expand(key)
        ssh_command = ['ssh',
                       '-o', 'StrictHostKeyChecking=no',
                       '-o', 'UserKnownHostsFile=/dev/null',
                       '-i', f'{key}',
                       '{host}',
                       f'{command}']

        result = Host.run(hosts=hosts,
                          command=ssh_command,
                          shell=False,
                          executor=executor)

        return result

    @staticmethod
    def put(hosts=None,
            source=None,
            destination=None,
            username=None,
            key="~/.ssh/id_rsa.pub",
            shell=False,
            processors=3,
            dryrun=False,
            verbose=False):
        """

        :param command: the command to be executed
        :param hosts: a list of hosts to be checked
        :param username: the usernames for the hosts
        :param key: the key for logging in
        :param processors: the number of parallel checks
        :return: list of dicts representing the ping result
        """

        if type(hosts) != list:
            hosts = Parameter.expand(hosts)

        key = path_expand(key)

        command = ['scp',
                   "-o", "StrictHostKeyChecking=no",
                   "-o", "UserKnownHostsFile=/dev/null",
                   '-i', key,
                   source,
                   "{host}:{destination}"]

        result = Host.run(hosts=hosts,
                          command=command,
                          destination=destination,
                          shell=False)

        return result

    @staticmethod
    def check(hosts=None,
              username=None,
              key="~/.ssh/id_rsa.pub",
              processors=3):
        #
        # BUG: this code has a bug and does not deal with different
        #  usernames on the host to be checked.
        #
        """

        :param hosts: a list of hosts to be checked
        :param username: the usernames for the hosts
        :param key: the key for logging in
        :param processors: the number of parallel checks
        :return: list of dicts representing the ping result
        """

        result = Host.ssh(hosts=hosts,
                          command='hostname',
                          username=username,
                          key=key,
                          processors=processors)

        return result

    # noinspection PyBroadException
    @staticmethod
    def _ping(args):
        """
            ping a vm

            :param args: dict of {ip address, count}
            :return: a dict representing the result, if returncode=0 ping is
                     successfully
            """
        ip = args['ip']
        count = str(args['count'])
        count_flag = '-n' if platform == 'windows' else '-c'
        command = ['ping', count_flag, count, ip]
        result = subprocess.run(command, capture_output=True)

        try:
            timers = result.stdout \
                .decode("utf-8") \
                .split("round-trip min/avg/max/stddev =")[1] \
                .replace('ms', '').strip() \
                .split("/")
            data = {
                "host": ip,
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "min": timers[0],
                "avg": timers[1],
                "max": timers[2],
                "stddev": timers[3]
            }
        except:
            data = {
                "host": ip,
                "success": result.returncode == 0,
                "stdout": result.stdout,
            }
        return data

    @staticmethod
    def ping(hosts=None, count=1, processors=3):
        """
        ping a list of given ip addresses

        :param hosts: a list of ip addresses
        :param count: number of pings to run per ip
        :param processors: number of processors to Pool
        :return: list of dicts representing the ping result
        """

        # first expand the ips to a list

        if type(hosts) != list:
            hosts = Parameter.expand(hosts)

            # wrap ip and count into one list to be sent to Pool map
        args = [{'ip': ip, 'count': count} for ip in hosts]

        with Pool(processors) as p:
            res = p.map(Host._ping, args)
            p.close()
            p.join()

        return res

    @staticmethod
    def ssh_keygen(hosts=None,
                   filename="~/.ssh/id_rsa",
                   username=None,
                   processors=3,
                   dryrun=False,
                   verbose=True):
        """
        generates the keys on the specified hosts.
        this fonction does not work well as it still will aski if we overwrite.

        :param hosts:
        :param filename:
        :param username:
        :param output:
        :param dryrun:
        :param verbose:
        :return:
        """
        if type(hosts) != list:
            hosts = Parameter.expand(hosts)

        command = f'ssh-keygen -q -N "" -f {filename} <<< y'
        result_keys = Host.ssh(hosts=hosts,
                               command=command,
                               username=username,
                               dryrun=dryrun,
                               processors=processors,
                               executor=os.system)
        result_keys = Host.ssh(hosts=hosts,
                               processors=processors,
                               command='cat .ssh/id_rsa.pub',
                               username=username)

        return result_keys

    @staticmethod
    def gather_keys(
        username=None,
        hosts=None,
        filename="~/.ssh/id_rsa.pub",
        key="~/.ssh/id_rsa",
        processors=3,
        dryrun=False):
        """
        returns in a list the keys of the specified hosts

        :param username:
        :param hosts:
        :param filename:
        :param key:
        :param dryrun:
        :return:
        """

        names = Parameter.expand(hosts)

        results_key = Host.ssh(hosts=names,
                               command='cat .ssh/id_rsa.pub',
                               username=username,
                               verbose=False)
        #results_authorized = Host.ssh(hosts=names,
        #                              command='cat .ssh/id_rsa.pub',
        #                              username=username,
        #                              verbose=False)
        filename = path_expand(filename)
        localkey = Shell.run(f'cat {filename}').strip()
        if results_key is None: # and results_authorized is None:
            return ""

        # geting the output and also removing duplicates
        output = list(set(
            [element["stdout"] for element in results_key]
            # + [element["stdout"] for element in results_authorized]
            + [localkey]

        ))

        output = '\n'.join(output)

        return output
