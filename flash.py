import xml.etree.ElementTree as ET
import paramiko
import tarfile
import os
from scp import SCPClient

CREDS = {
    'host' : '<host_ip_addr>',
    'user' : '<user>',
    'pw' : '<password>',
    'host_project_path' : '/home/user/build',
    'contents' : 'contents.xml',
    'pf' : '8155',
    'st' : 'ufs'
}

TEMP_DIR = '/temp_dir'
TARGET_TAR = 'build-out.tar.bz2'

def find_rec(node, element, result, dir=None):
    for item in node:
        if item.tag == 'build':
            dir = item.findall('name')
            if len(dir) > 0:
                dir = dir[0].text
            else:
                dir = None
        if item.tag == element:
            result.append((item, dir))
        find_rec(item, element, result, dir)
    return result

def check_parent_dir(dir):
    if dir == None or dir == 'common':
        return False
    return True

def get_fastboot_files_paths(files, pf, st, types=['fastboot', 'fastboot_complete', 'gpt_file']):
    images = {}
    for item, dir in files:
        file_path = ''
        file_name = ''
        partition = None
        correct_type = False
        correct_pf = True
        pf_in_parent = False
        for attr in item.attrib:
            for typ in types:
                if attr == typ:
                    correct_type = True
                    # should be only one attr fastboot || fastboot_complete || gpt
                    partition = item.attrib[attr]
            if attr == 'flavor':
                if item.attrib[attr] != pf:
                    correct_pf = False
                pf_in_parent = True

        if correct_type and correct_pf:
            name = item.findall('file_name')[0].text
            paths = item.findall('file_path')
            path = None
            # todo: check if redundant code
            if pf_in_parent:
                path = paths[0].text
                if dir != None and dir != 'common':
                    path = dir + '/' + path
                if path.endswith('/'):
                    images[name] = (path + name, partition)
                if not path.endswith('/'):
                    images[name] = (path + '/' + name, partition)
            else:
                for pat in paths:
                    if pat.attrib['flavor'] == pf:
                        path = pat.text
                        if dir != None and dir != 'common':
                            path = dir + '/' + path
                        if path.endswith('/'):
                            images[name] = (path + name, partition)
                        if not path.endswith('/'):
                            images[name] = (path + '/' + name, partition)
    return images

def main():
    # Parse contents.xml
    root = ET.parse(CREDS['contents']).getroot()
    files = []
    find_rec(root, 'download_file', files)
    files = get_fastboot_files_paths(files, '8155', 'ufs')

    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(CREDS['host'], 22, CREDS['user'], CREDS['pw'])

    with SCPClient(ssh.get_transport()) as scp:
        print('----- Compressing files -----')
        temp_path = CREDS['host_project_path'] + TEMP_DIR
        print('-- Create temp dir')
        ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command('mkdir -p ' + temp_path)
        print(ssh_stderr.read())

        flash_dict = {}
        # Copy files to temp dir
        for name, (path, partition) in files.items():
            answer = None
            while answer not in ("y", "n", "c", ""):
                answer = input("Download " + path + " to '" + partition + "'? [Y]es / [n]o / [c]hange: ")
                answer = answer.lower()
                if answer == 'n':
                    continue
                elif answer == 'c' or answer == 'y' or answer == "":
                    if answer == 'c' or partition == "true":
                        partition = input("Enter partition name:")
                else:
                    print("Please answer y/n/c")
            if answer == 'n':
                continue

            print("copying '" + name + "' as '" + partition +"' partition")
            cmd = 'cp ' + CREDS['host_project_path'] + '/' + path + ' ' + temp_path
            ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command(cmd)
            print(ssh_stderr.read())
            flash_dict[partition] = name

        # Compress temp dir and downlaod to local folder
        cm_file = CREDS['host_project_path'] + '/' + TARGET_TAR + '.tar.bz2'
        cmd = 'tar -pcjvf ' + cm_file + ' -C' + temp_path + ' .'
        print("Compressing...")
        ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command(cmd)
        print(ssh_stderr.read())
        print("Copying...")
        scp.get(cm_file, TARGET_TAR)

    askEachFile = False
    answer = None
    while answer not in ("a", "n", "c", ""):
        answer = input("Flash downloaded files? [A]ll / [n]one / [c]hoose ")
        answer = answer.lower()
        if answer == 'n':
            exit
        elif answer == 'a' or answer == "":
            continue
        elif answer == 'c':
            askEachFile = true
            continue
        else:
            print("Please answer y/n")

    print("Decompressing...")
    # TARGET_TAR
    tf = tarfile.open('snapdragon-auto-gen3-lv-0-1_hlos_dev-out.tar.bz2')
    tf.extractall()

    print("Flashing...")
    for partition, name in flash_dict.items():
        answer = None
        while answer not in ("y", "n", ""):
            if askEachFile:
                answer = input("Flash '" + name + "'  to '" + partition + "'? [Y]es / [n]o: ")
            else:
                answer = 'y'

            answer = answer.lower()
            if answer == 'n':
                continue
            elif answer == 'y' or answer == "":
                print("Flashing " + name + ' to ' + partition)
                os.system('fastboot flash ' + partition + ' ' + name)
            else:
                print("Please answer y/n")

if __name__ == '__main__':
    main()
