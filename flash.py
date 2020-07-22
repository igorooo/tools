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

# get all files specified in tag 'download_file' with attribs fastboot || fastboot_complete || gpt_file
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
    files = get_fastboot_files_paths(files, CREDS['pf'], CREDS['st'])

    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(CREDS['host'], 22, CREDS['user'], CREDS['pw'])

    with SCPClient(ssh.get_transport()) as scp:
        print('----- Compressing files -----')
        temp_path = CREDS['host_project_path'] + TEMP_DIR
        print('-- Create temp dir: ' + temp_path)
        ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command('mkdir -p ' + temp_path)
        print(ssh_stderr.read())

        flash_dict = {}
        allimgs = True
        y = input("Downlaod all images? [If no press 'n' + Enter]")
        if y == 'n':
            allimgs = False
        # Copy files to temp dir
        for name, (path, partition) in files.items():
            if allimgs == False:
                y = input("Skip downloading " + name + "? [If yes press 'y' + Enter]")
                if y == 'y':
                    print('Skipping ' + name)
                    continue
            #print("copy: " + name)
            cmd = 'cp ' + CREDS['host_project_path'] + '/' + path + ' ' + temp_path
            ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command(cmd)
            print(ssh_stderr.read())
            flash_dict[partition] = name

        # Compress temp dir and download to local folder
        cm_file = CREDS['host_project_path'] + '/' + TARGET_TAR + '.tar.bz2'
        cmd = 'tar -pcjvf ' + cm_file + ' -C' + temp_path + ' .'
        ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command(cmd)
        print(ssh_stderr.read())
        scp.get(cm_file, TARGET_TAR)

    tf = tarfile.open(TARGET_TAR)
    tf.extractall()

    flash_dict = sorted(flash_dict.items(), key=sort_key)

    print('------------------------------------')
    for part in flash_dict:
        print(part)
    print('------------------------------------')

    y = input("Skip flashing? [If yes press 'y' + Enter]")
    if y == 'y':
        return

    for partition, name in flash_dict:
        if partition == 'true':
            partition = input('Enter partition for' + name + ':')
        else:
            y = input('Flash ' + name + ' to ' + partition + "? [If no press 'n' and Enter]")
            if y == 'n':
                partition = input('Enter new partition for +' + name + ':')
        print("Flashing " + name + ' (partition)')
        os.system('fastboot flash ' + partition + ' ' + name)

def sort_key(item):
    if 'partition:' in item[0]:
        temp = str(item[0])
        return int(temp.replace('partition:', ''))
    else:
        # any number larger than gpt partitions number
        return 100

if __name__ == '__main__':
    main()
