#!/bin/sh

set -e

usage() {
    echo "Usage: bup import-rdiff-backup [-n]" \
        "<path to rdiff-backup root> <backup name>"
    echo "-n,--dry-run: just print what would be done"
    exit 1
}

control_c() {
    echo "bup import-rdiff-backup: signal 2 received" 1>&2
    exit 128
}

trap control_c INT

dry_run=
while [ "$1" = "-n" -o "$1" = "--dry-run" ]; do
    dry_run=echo
    shift
done

bup()
{
    $dry_run "${BUP_MAIN_EXE:=bup}" "$@"
}

snapshot_root=$1
branch=$2

[ -n "$snapshot_root" -a "$#" = 2 ] || usage

if [ ! -e "$snapshot_root/." ]; then
    echo "'$snapshot_root' isn't a directory!"
    exit 1
fi


backups=$(rdiff-backup --list-increments --parsable-output "$snapshot_root")
backups_count=$(echo "$backups" | wc -l)
counter=1
echo "$backups" |
while read timestamp type; do
    tmpdir=$(mktemp -d)

    echo "Importing backup from $(date --date=@$timestamp +%c) " \
        "($counter / $backups_count)" 1>&2
    echo 1>&2

    echo "Restoring from rdiff-backup..." 1>&2
    rdiff-backup -r $timestamp "$snapshot_root" "$tmpdir"
    echo 1>&2

    echo "Importing into bup..." 1>&2
    TMPIDX=$(mktemp -u)
    bup index -ux -f "$tmpidx" "$tmpdir"
    bup save --strip --date="$timestamp" -f "$tmpidx" -n "$branch" "$tmpdir"
    rm -f "$tmpidx"

    rm -rf "$tmpdir"
    counter=$((counter+1))
    echo 1>&2
    echo 1>&2
done
