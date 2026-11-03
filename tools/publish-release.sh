#!/usr/bin/env bash
# Publishes one tagged version of Corpus to the customers' repository
# (github.com/corpuskb/Corpus): the files of that tag as one commit, without
# this repository's history. Customers update with `git pull`.
#
#   tools/publish-release.sh v1.0.0
#
# The tag must exist here and match `version` in backend/pyproject.toml.
# Paths marked export-ignore in .gitattributes (this script among them) stay out.
set -euo pipefail

tag=${1:?usage: tools/publish-release.sh vX.Y.Z}
remote=${CORPUS_RELEASE_REMOTE:-https://github.com/corpuskb/Corpus.git}
root=$(git rev-parse --show-toplevel)
version=${tag#v}

git -C "$root" rev-parse -q --verify "refs/tags/$tag^{commit}" >/dev/null ||
  { echo "No tag $tag in this repository." >&2; exit 1; }
git -C "$root" show "$tag:backend/pyproject.toml" | grep -q "^version = \"$version\"$" ||
  { echo "Tag $tag does not match the version in backend/pyproject.toml." >&2; exit 1; }

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
git clone --quiet "$remote" "$work/corpus" 2>/dev/null
cd "$work/corpus"
# Releases follow each other on main; the first one starts it.
git checkout -q main 2>/dev/null || git checkout -q --orphan main

if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
  echo "$tag is already published." >&2
  exit 1
fi

# The release replaces every file: what the tag removed disappears for customers too.
git rm -rq --ignore-unmatch .
git -C "$root" archive "$tag" | tar -x
git add -A
git commit -qm "Corpus $version"
git tag -a "$tag" -m "Corpus $version"
git push -q origin HEAD:main "$tag"
echo "Published Corpus $version to $remote."
