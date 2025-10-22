mkdir -p /Volumes/LRZ
sshfs -o volname=LRZ,reconnect,ServerAliveInterval=15,ServerAliveCountMax=3,auto_cache,defer_permissions,IdentityFile="$HOME/.ssh/id_rsa" \
  ge57gon2@login.ai.lrz.de:/dss/dssfs04/lwp-dss-0002/pn36ni/pn36ni-dss-0000/ge57gon2/projects \
  /Volumes/LRZ
