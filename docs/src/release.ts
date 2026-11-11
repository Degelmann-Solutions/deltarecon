// The release the documentation applies to. The number stands in
// release.json and nowhere else under docs/; it is renewed by hand when a
// release is published. It is not read from pyproject.toml, whose version is
// raised before a release is published.
import release from './release.json';

export const version: string = release.version;
export const tag = `v${version}`;
