#!/usr/bin/python3

import os
import subprocess
import sys
from src.installer_core import * # NOQA
#from src.installer_core import is_luks, ash_chroot, clear, deploy_base_snapshot, deploy_to_common, get_hostname, get_timezone, grub_ash, is_efi, post_bootstrap, pre_bootstrap, unmounts
from setup import args, distro

def initram_update_luks():
    if is_luks:
        os.system("sudo dd bs=512 count=4 if=/dev/random of=/mnt/etc/crypto_keyfile.bin iflag=fullblock")
        os.system("sudo chmod 000 /mnt/etc/crypto_keyfile.bin") # Changed from 600 as even root doesn't need access
        os.system(f"sudo cryptsetup luksAddKey {args[1]} /mnt/etc/crypto_keyfile.bin")
        os.system("sudo sed -i -e 's|^#KEYFILE_PATTERN=|KEYFILE_PATTERN='/etc/crypto_keyfile.bin'|' /mnt/etc/cryptsetup-initramfs/conf-hook")
        os.system("sudo echo UMASK=0077 >> /mnt/etc/initramfs-tools/initramfs.conf")
        os.system("sudo echo 'cryptroot '${args[1]}'  /etc/crypto_keyfile.bin luks.discard.key-slot=1' | sudo tee -a /mnt/etc/crypttab")
        os.system(f"sudo chroot /mnt update-initramfs -u")

#   1. Define variables
ARCH = "amd64"
RELEASE = "bullseye"
KERNEL = ""
packages = f"linux-image-{ARCH} btrfs-progs sudo curl python3 python3-anytree dhcpcd5 network-manager locales nano kicksecure-cli deb-multimedia-keyring cryptsetup cryptsetup-initramfs cryptsetup-run console-setup" # firmware-linux-nonfree os-prober
super_group = "sudo"
v = "" # GRUB version number in /boot/grubN
tz = get_timezone()
hostname = get_hostname()
#hostname = subprocess.check_output("git rev-parse --short HEAD", shell=True).decode('utf-8').strip() # Just for debugging

#   Pre bootstrap
pre_bootstrap()

#excl = subprocess.check_output("dpkg-query -f '${binary:Package} ${Priority}\n' -W | grep -v 'required\|important' | awk '{print $1}'", shell=True).decode('utf-8').strip().replace("\n",",")
os.system(f"sed 's/RELEASE/{RELEASE}/g' ./src/distros/{distro}/sources.list | sudo tee tmp_sources.list")
excode = os.system(f"sudo SECURITY_MISC_INSTALL=force DERIVATIVE_APT_REPOSITORY_OPTS=stable anon_shared_inst_tb=open mmdebstrap --skip=check/empty --arch {ARCH}  --include='{packages}' --variant=required {RELEASE} /mnt tmp_sources.list") ### --include={packages} ? --variant=minbase ?
excode = os.system(f"sudo rm /mnt/etc/apt/sources.list.d/*tmp_sources.list")
if excode != 0:
    sys.exit("Failed to bootstrap!")

#   Mount-points for chrooting
ash_chroot()

# Install anytree and necessary packages in chroot
os.system("sudo systemctl start ntp && sleep 30s && ntpq -p") # Sync time in the live iso
os.system(f"echo 'deb [trusted=yes] https://www.deb-multimedia.org {RELEASE} main' | sudo tee -a /mnt/etc/apt/sources.list.d/multimedia.list{DEBUG}")
excode = os.system(f"sudo chroot /mnt apt-get -y update")
excode = os.system(f"sudo chroot /mnt apt-get -y install --no-install-recommends --fix-broken {packages}")
if excode != 0:
    sys.exit("Failed to download packages!")
if is_efi:
    excode = os.system("sudo chroot /mnt apt-get -y install --no-install-recommends grub-efi") ### efibootmgr does get installed. Does this do it?
    if excode != 0:
        sys.exit("Failed to install grub!")
else:
    excode = os.system("sudo chroot /mnt apt-get -y install --no-install-recommends grub-pc")
    if excode != 0:
        sys.exit("Failed to install grub!")

#   3. Package manager database and config files
os.system("sudo mv /mnt/var/lib/dpkg /mnt/usr/share/ash/db/")
os.system("sudo ln -srf /mnt/usr/share/ash/db/dpkg /mnt/var/lib/dpkg")

#   4. Update hostname, hosts, locales and timezone, hosts
os.system(f"echo {hostname} | sudo tee /mnt/etc/hostname")
os.system(f"echo 127.0.0.1 {hostname} {distro} | sudo tee -a /mnt/etc/hosts")
#os.system("sudo chroot /mnt sudo localedef -v -c -i en_US -f UTF-8 en_US.UTF-8")
os.system("sudo sed -i 's|^#en_US.UTF-8|en_US.UTF-8|g' /mnt/etc/locale.gen")
os.system("sudo chroot /mnt sudo locale-gen")
os.system("echo 'LANG=en_US.UTF-8' | sudo tee /mnt/etc/locale.conf")
os.system(f"sudo ln -srf /mnt{tz} /mnt/etc/localtime")
os.system("sudo chroot /mnt sudo hwclock --systohc")

#   Post bootstrap
post_bootstrap(super_group)

#   5. Change password for default user
os.system("sudo chroot /mnt passwd user")

#   6. Services (init, network, etc.)
os.system("sudo chroot /mnt systemctl enable NetworkManager")

#   7. Boot and EFI
initram_update_luks()
grub_ash(v)

#   BTRFS snapshots
deploy_base_snapshot()

#   Copy boot and etc: deployed snapshot <---> common
deploy_to_common()

#   Unmount everything and finish
unmounts()

clear()
print("Installation complete!")
print("You can reboot now :)")

