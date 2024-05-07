#!/usr/bin/env python3

"""Release Note Tool

This script partially automates the process of publishing release
notes for engineering candidate and release candidate builds of
MicroShift.

The script expects to be run in multiple phases.

*Tagging*

First, it looks for the most recent RPM to have been published to the
mirror, and uses information encoded in that filename to determine the
SHA of the commit that was used for the build and the version number
given to it.

Then it looks for that tag in the local repository. If there is no tag
already, it emits instructions for tagging the correct commit and
pushing the tag to GitHub.

*Draft Release*

After the tag is present, running the script again causes it produce a
draft release with a preamble that includes download URLs and a body
that is auto-generated by GitHub's service based on the pull requests
that have merged since the last tagged release.

*Publishing Release*

The script creates a draft release, which must be published by hand to
make it public. Open the link printed at the end of the script run and
use the web interface to review and then publish the release.

NOTE:

  To use this script, you must have either

    A GitHub token configured in the environment variable GITHUB_TOKEN
    with enough privileges on the openshift/microshift repository to
    create releases.

  OR

    A GitHub application ID configured in the environment variable
    APP_ID and a client key with the file name configured in the
    CLIENT_KEY environment variable.

"""

import argparse
import collections
import datetime
import html.parser
import json
import os
import pathlib
import re
import subprocess
import textwrap
import urllib
from urllib import request

import github

URL_BASE = "https://mirror.openshift.com/pub/openshift-v4/aarch64/microshift"
URL_BASE_X86 = "https://mirror.openshift.com/pub/openshift-v4/x86_64/microshift"
GITHUB_ORG = 'openshift'
GITHUB_REPO = 'microshift'
REMOTE = "token-remote"
MAX_RELEASE_NOTE_BODY_SIZE = 125000
TRUNCATED_MESSAGE = '\n\n(release notes were truncated)\n\n'

# An EC RPM filename looks like
# microshift-4.13.0~ec.4-202303070857.p0.gcf0bce2.assembly.ec.4.el9.aarch64.rpm
# an RC RPM filename looks like
# microshift-4.13.0~rc.0-202303212136.p0.gbd6fb96.assembly.rc.0.el9.aarch64.rpm
VERSION_RE = re.compile(
    r"""
    microshift-                             # prefix
    (?P<full_version>
      (?P<product_version>\d+\.\d+\.\d+)    # product version
      ~                                     # separator
      (?P<candidate_type>ec|rc)\.(?P<candidate_number>\d+)  # which candidate of which type
      -
      (?P<release_date>\d+)\.               # date
      p(?P<patch_num>\d+)\.                 # patch number
      g(?P<commit_sha>[\dabcdef]+)          # commit SHA prefix
    )\.
    """,
    re.VERBOSE,
)

# Save our token for use later
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')


# Representation of one release
Release = collections.namedtuple(
    'Release',
    "release_name commit_sha product_version candidate_type candidate_number release_type release_date",
)


def main():
    """
    The main function of the script. It runs the `check_one()` function for both 'ocp-dev-preview'
    and 'ocp' release types and for a specified version depending upon provided arguments.
    """
    global GITHUB_TOKEN

    # The script runs as
    # .../microshift/scripts/release-notes/gen_ec_release_notes.py
    # and we want the path to
    # .../microshift
    root_dir = pathlib.Path(__file__).parent.parent.parent
    version_makefile = root_dir / 'Makefile.version.aarch64.var'
    # Makefile contains something like
    #   OCP_VERSION := 4.16.0-0.nightly-arm64-2024-03-13-041907
    # and we want this ^^^^
    #
    # We get it as ['4', '16'] to make the next part of the process of
    # building the list of versions to scan easier.
    _full_version = version_makefile.read_text('utf8').split('=')[-1].strip()
    major, minor = _full_version.split('.')[:2]

    # We build a default list of versions to scan using the current
    # version and the previous version. This assumes the script is run
    # out of the main branch where we can find the most current
    # version under development. During the period where 4.n is being
    # developed, 4.n-1 may still be producing only release candidates,
    # so that scanning those 2 versions give us the 2 most recent
    # candidates for having no releases. During the period where the
    # main branch has not landed a rebase to update the version and
    # both main and the pre-release branch have the same version, we
    # will end up scanning for EC or RC releases of 4.n-2, but that's
    # OK because the should all have been tagged already.
    versions_to_scan = [
        '.'.join([major, minor]),              # this minor version
        '.'.join([major, str(int(minor)-1)]),  # the previous minor version
    ]

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '--ec',
        action='store_true',
        default=True,
        dest='ec',
        help='Include engineering candidates (default)',
    )
    parser.add_argument(
        '--no-ec',
        action='store_false',
        dest='ec',
        help='Do not include engineering candidates',
    )
    parser.add_argument(
        '--rc',
        action='store_true',
        default=True,
        help='Include release candidates (default)',
    )
    parser.add_argument(
        '--no-rc',
        action='store_false',
        dest='rc',
        help='Do not include release candidates',
    )
    parser.add_argument(
        '-n', '--dry-run',
        action='store_true',
        dest='dry_run',
        default=False,
        help='Report but take no action',
    )
    parser.add_argument(
        '--version-to-scan',
        action='append',
        dest='versions_to_scan',
        default=[],
        help=('A version to scan. May be repeated. ' +
              f'Defaults to {versions_to_scan} but if any version ' +
              'is given on the command line the default is overridden.'),
    )
    args = parser.parse_args()

    if not GITHUB_TOKEN:
        print('GITHUB_TOKEN is not set, trying to authenticate using application credentials')
        GITHUB_TOKEN = get_access_token_for_app()
    if not GITHUB_TOKEN:
        raise RuntimeError('GITHUB_TOKEN does not appear to be set')

    # If the user has given us versions to scan, do not use the
    # computed defaults.
    if args.versions_to_scan:
        versions_to_scan = args.versions_to_scan

    new_releases = []
    if args.ec:
        new_releases.extend(find_new_releases(versions_to_scan, URL_BASE, 'ocp-dev-preview'))
        new_releases.extend(find_new_releases(versions_to_scan, URL_BASE_X86, 'ocp-dev-preview'))
    if args.rc:
        new_releases.extend(find_new_releases(versions_to_scan, URL_BASE, 'ocp'))
        new_releases.extend(find_new_releases(versions_to_scan, URL_BASE_X86, 'ocp'))

    if not new_releases:
        print("No new releases found.")
        return

    print()
    add_token_remote()

    unique_releases = {
        r.commit_sha: r
        for r in new_releases
    }

    for new_release in unique_releases.values():
        publish_release(new_release, not args.dry_run)


def get_access_token_for_app():
    """Return an access token for a GitHub App."""
    app_id = os.environ.get('APP_ID')
    if not app_id:
        raise RuntimeError('APP_ID is not set')
    key_path = os.environ.get('CLIENT_KEY')
    if not key_path:
        raise RuntimeError('CLIENT_KEY is not set')
    integration = github.GithubIntegration(
        app_id,
        pathlib.Path(key_path).read_text(encoding='utf-8'),
    )
    app_installation = integration.get_installation(GITHUB_ORG, GITHUB_REPO)
    if app_installation is None:
        raise RuntimeError(
            f"Failed to get app_installation for {GITHUB_ORG}/{GITHUB_REPO}. " +
            f"Response: {app_installation.raw_data}"
        )
    return integration.get_access_token(app_installation.id).token


class VersionListParser(html.parser.HTMLParser):
    """HTMLParser to extract version numbers from the mirror file list pages.

    A page like https://mirror.openshift.com/pub/openshift-v4/aarch64/microshift/ocp-dev-preview/

    contains HTML like

        <tr class="file">
            <td></td>
            <td>
                <a href="4.12.0-rc.6/">
                    <svg width="1.5em" height="1em" version="1.1" viewBox="0 0 265 323"><use xlink:href="#folder"></use></svg>
                    <span class="name">4.12.0-rc.6</span>
                </a>
            </td>
            <td data-order="-1">&mdash;</td>
            <td class="hideable"><time datetime="">-</time></td>
            <td class="hideable"></td>
        </tr>

    so we look for the 'span' tags with class 'name' and extract the
    text between the tags as the version.
    """

    def __init__(self):
        super().__init__()
        self._in_version = False
        self.versions = []

    def handle_starttag(self, tag, attrs):
        if tag != 'span':
            return
        attr_d = dict(attrs)
        self._in_version = attr_d.get('class', '') == 'name'

    def handle_endtag(self, tag):
        self._in_version = False

    def handle_data(self, data):
        if not self._in_version:
            return
        data = data.strip()
        if not data:
            return
        if data.startswith('latest-'):
            return
        self.versions.append(data)

    def error(self, message):
        "Handle an error processing the HTML"
        print(f"WARNING: error processing HTML: {message}")


def find_new_releases(versions_to_scan, url_base, release_type):
    """Returns a list of Release instances for missing releases.
    """
    new_releases = []
    # Get the list of the latest RPMs for the release type and vbersion.
    version_list_url = f"{url_base}/{release_type}/"
    with request.urlopen(version_list_url) as response:
        content = response.read().decode("utf-8")
    parser = VersionListParser()
    parser.feed(content)
    for version in parser.versions:
        # Skip very old RCs, indicated by the first 2 parts of the
        # version string major.minor.
        version_prefix = '.'.join(version.split('.')[:2])
        if version_prefix not in versions_to_scan:
            continue
        try:
            nr = check_for_new_releases(url_base, release_type, version)
            if nr:
                new_releases.append(nr)
        except Exception as err:  # pylint: disable=broad-except
            print(f"WARNING: could not process {release_type} {version}: {err}")
    return new_releases


def check_for_new_releases(url_base, release_type, version):
    """
    Checks the latest RPMs for a given release type and version,
    and returns a Release instance for any that don't exist.
    """
    # Get the list of the latest RPMs for the release type and
    # version. Different versions use different "os name" components
    # in the path.
    for os_name in ['el9', 'elrhel-9']:
        rpm_list_url = f"{url_base}/{release_type}/{version}/{os_name}/os/rpm_list"
        print(f"\nFetching {rpm_list_url} ...")
        try:
            with request.urlopen(rpm_list_url) as rpm_list_response:
                rpm_list = rpm_list_response.read().decode("utf-8").splitlines()
        except Exception as err:
            print(err)
        else:
            break

    # Look for the RPM for MicroShift itself, with a name like
    #
    # Packages/microshift-4.13.0~ec.3-202302130757.p0.ge636e15.assembly.ec.3.el8__aarch64/microshift-4.13.0~ec.3-202302130757.p0.ge636e15.assembly.ec.3.el8.aarch64.rpm
    #
    # then parse out the EC version number and other details needed to
    # build the release tag.
    version_prefix = version.partition('-')[0]
    microshift_rpm_name_prefix = f"microshift-{version_prefix}"
    microshift_rpm_filename = None
    for package_path in rpm_list:
        parts = package_path.split("/")
        if parts[-1].startswith(microshift_rpm_name_prefix):
            microshift_rpm_filename = parts[-1]
            break
    else:
        rpm_names = ',\n'.join(rpm_list)
        print(f"WARNING: Did not find {microshift_rpm_name_prefix} in {rpm_names}")
        return None

    print(f"Examining RPM {microshift_rpm_filename}")

    match = VERSION_RE.search(microshift_rpm_filename)
    if match is None:
        raise RuntimeError(f"Could not parse version info from '{microshift_rpm_filename}'")
    rpm_version_details = match.groupdict()
    product_version = rpm_version_details["product_version"]
    candidate_type = rpm_version_details["candidate_type"]
    candidate_number = rpm_version_details["candidate_number"]
    release_date = rpm_version_details["release_date"]
    patch_number = rpm_version_details["patch_num"]
    commit_sha = rpm_version_details["commit_sha"]

    # Older release names # look like "4.13.0-ec-2" but we had a few
    # sprints where we published multiple builds, so use more of the
    # version details as the release name now.
    #
    # 4.14.0~ec.3-202307170726.p0
    release_name = f"{product_version}-{candidate_type}.{candidate_number}-{release_date}.p{patch_number}"

    # Check if the release already exists
    print(f"Checking for release {release_name}...")
    if github_release_exists(release_name):
        print("Found an existing release, no work to do")
        return None
    print("Not found")

    return Release(
        release_name,
        commit_sha,
        product_version,
        candidate_type,
        candidate_number,
        release_type,
        release_date,
    )


def tag_exists(release_name):
    "Checks if a given tag exists in the local repository."
    try:
        subprocess.run(["git", "show", release_name],
                       stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL,
                       check=True)
        return True
    except subprocess.CalledProcessError:
        return False


def add_token_remote():
    """
    Adds the Git remote to the given repository using
    the provided installation (or personal) access token.
    """
    env = {}
    env.update(os.environ)

    print(f'git remote remove {REMOTE}')
    subprocess.run(
       ["git", "remote", "remove", REMOTE],
       env=env,
    )
    print(f'git remote add {REMOTE} ~~REDACTED~~')
    remote_url = f"https://x-access-token:{GITHUB_TOKEN}@github.com/{GITHUB_ORG}/{GITHUB_REPO}"
    result = subprocess.run(
       ["git", "remote", "add", REMOTE, remote_url],
       env=env,
       capture_output=True,
       text=True,
    )
    if result.returncode != 0:
        err = result.stderr.replace(GITHUB_TOKEN, "") if result.stderr else "stderr is empty"
        raise Exception(f"Command `git remote add` failed: {err}")


def get_previous_tag(release_name):
    "Returns the name of the tag _before_ release_name on the branch."
    output = subprocess.check_output(["git", "describe", f'{release_name}~1', '--abbrev=0'])
    return output.decode('utf-8').strip()


def tag_release(tag, sha, buildtime):
    env = {}
    # Include our existing environment settings to ensure values like
    # HOME and other git settings are propagated.
    env.update(os.environ)
    timestamp = buildtime.strftime('%Y-%m-%d %H:%M')
    env['GIT_COMMITTER_DATE'] = timestamp
    print(f'GIT_COMMITTER_DATE={timestamp} git tag {tag} {sha}')
    subprocess.run(
        ['git', 'tag', '-m', tag, tag, sha],
        env=env,
        check=True,
    )


def push_tag(tag):
    env = {}
    # Include our existing environment settings to ensure values like
    # HOME and other git settings are propagated.
    env.update(os.environ)
    print(f'git push {REMOTE} {tag}')
    cmd = ['git', 'push', REMOTE, tag]
    completed = subprocess.run(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = completed.stdout.decode('utf-8') if completed.stdout else ''
    if completed.returncode != 0:
        raise subprocess.CalledProcessError(completed.returncode, cmd, output)


def publish_release(new_release, take_action):
    """Does the work to tag and publish a release.
    """
    release_name = new_release.release_name
    commit_sha = new_release.commit_sha
    product_version = new_release.product_version
    candidate_type = new_release.candidate_type
    candidate_number = new_release.candidate_number
    release_type = new_release.release_type
    release_date = new_release.release_date

    # Set up the release notes preamble with download links
    preamble = textwrap.dedent(f"""
    This is a candidate release for {product_version}.

    See the mirror for build artifacts:
    - {URL_BASE_X86}/{release_type}/{product_version}-{candidate_type}.{candidate_number}/
    - {URL_BASE}/{release_type}/{product_version}-{candidate_type}.{candidate_number}/

    Or add this RPM repository to your x86 systems:

    ```
    [microshift-{product_version}-{candidate_type}-{candidate_number}]
    name=MicroShift {product_version} EarlyAccess {candidate_type}.{candidate_number} RPMs
    baseurl={URL_BASE_X86}/{release_type}/{product_version}-{candidate_type}.{candidate_number}/el9/os/
    enabled=1
    gpgcheck=0
    skip_if_unavailable=0
    ```

    or for aarch64 systems:

    ```
    [microshift-{product_version}-{candidate_type}-{candidate_number}]
    name=MicroShift {product_version} EarlyAccess {candidate_type}.{candidate_number} RPMs
    baseurl={URL_BASE}/{release_type}/{product_version}-{candidate_type}.{candidate_number}/el9/os/
    enabled=1
    gpgcheck=0
    skip_if_unavailable=0
    ```

    """)

    if not tag_exists(release_name):
        # release_date looks like 202402022103
        buildtime = datetime.datetime.strptime(release_date, '%Y%m%d%H%M')
        tag_release(release_name, commit_sha, buildtime)

    # Get the previous tag on the branch as the starting point for the
    # release notes.
    previous_tag = get_previous_tag(release_name)

    # Auto-generate the release notes ourselves, add the preamble,
    # then make sure the results fit within the size limits imposed by
    # the API.
    generated_notes = github_release_notes(previous_tag, release_name, commit_sha)
    notes = f'{preamble}\n{generated_notes["body"]}'
    if len(notes) > MAX_RELEASE_NOTE_BODY_SIZE:
        lines = notes.splitlines()
        last_line = lines[-1]
        notes_content_we_can_truncate = notes[:-len(last_line)]
        amount_we_can_keep = MAX_RELEASE_NOTE_BODY_SIZE - len(last_line) - len(TRUNCATED_MESSAGE)
        truncated = notes_content_we_can_truncate[:amount_we_can_keep]
        if truncated[-1] == '\n':
            notes_to_keep = truncated
        else:
            # don't leave a partial line
            notes_to_keep = truncated.rpartition('\n')[0].rstrip()
        notes = f'{notes_to_keep}{TRUNCATED_MESSAGE}{last_line}'

    if not take_action:
        print(f'Dry run for new release {new_release} on commit {commit_sha} from {release_date}')
        print(notes)
        return

    push_tag(release_name)

    # Create draft release with message that includes download URLs and history
    try:
        github_release_create(release_name, notes)
    except urllib.error.URLError as e:
        print(f"Failed to create the release {release_name}: {e}")
        print(f"Response: {str(e.fp.readlines())}")
        raise
    except Exception as err:
        print(f"Failed to create the release {release_name}: {err}")
        raise


def github_release_create(tag, notes):
    results = github_api(
        f'/repos/{GITHUB_ORG}/{GITHUB_REPO}/releases',
        tag_name=tag,
        name=tag,
        body=notes,
        draft=False,
        prerelease=True,
    )
    print(f'Created new release {tag}')
    print()
    print(results['html_url'])
    print()
    print(results['body'])


def github_release_notes(previous_tag, tag_name, target_commitish):
    results = github_api(
        f'/repos/{GITHUB_ORG}/{GITHUB_REPO}/releases/generate-notes',
        tag_name=tag_name,
        target_commitish=target_commitish,
        previous_tag_name=previous_tag,
    )
    return results


def github_release_exists(tag):
    try:
        github_api(f'/repos/{GITHUB_ORG}/{GITHUB_REPO}/releases/tags/{tag}')
        return True
    except Exception:
        return False


def github_api(path, **data):
    url = f'https://api.github.com/{path.lstrip("/")}'
    if data:
        r = request.Request(
            url=url,
            data=json.dumps(data).encode('utf-8'),
        )
    else:
        r = request.Request(url=url)
    print(r.get_method(), url, data)
    r.add_header('Accept', 'application/vnd.github+json')
    r.add_header('User-agent', 'microshift-release-notes')
    r.add_header('Authorization', f'Bearer {GITHUB_TOKEN}')
    r.add_header('X-GitHub-Api-Version', '2022-11-28')
    response = request.urlopen(r)
    return json.loads(response.read().decode('utf-8'))


if __name__ == "__main__":
    main()
