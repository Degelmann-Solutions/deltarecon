// The release the documentation applies to. The number stands in
// release.json and nowhere else under docs/; it is renewed by hand when a
// release is published. It is not read from pyproject.toml, whose version is
// raised before a release is published.
//
// release.json also holds the SHA-256 of the archive of each platform, as
// `SHA256SUMS` of the release names it; `npm run check:release` holds both
// against the release. The names of the archives and of the package folders
// follow from the number.
import release from './release.json';
import { outside } from './site';

export type Platform = 'windows' | 'linux';

/** The platforms a package exists for, Windows first. */
export const platforms: readonly Platform[] = ['windows', 'linux'];

export const version: string = release.version;
export const tag = `v${version}`;

/** The page of the release on GitHub, where the reader downloads the archive. */
export const releasePage = `${outside.repository}/releases/tag/${tag}`;

/** The file beside the archives that names the SHA-256 of each. */
export const sumsFile = 'SHA256SUMS';

const targets: Record<Platform, { triple: string; extension: string }> = {
  windows: { triple: 'x86_64-pc-windows-msvc', extension: 'zip' },
  linux: { triple: 'x86_64-unknown-linux-gnu', extension: 'tar.gz' },
};

/** The folder an archive unpacks to: the package folder. */
export function packageFolder(platform: Platform): string {
  return `deltarecon-${version}-${targets[platform].triple}`;
}

/** The archive of a platform: its file name and its SHA-256. */
export function archive(platform: Platform): { file: string; sha256: string } {
  return {
    file: `${packageFolder(platform)}.${targets[platform].extension}`,
    sha256: release.sha256[platform],
  };
}
