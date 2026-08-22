//go:build unit

package service

import (
	"context"
	"errors"
	"fmt"
	"runtime"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

var errUpdateDownloadStopped = errors.New("stop after selecting download")

type updateServiceCacheStub struct {
	data string
}

func (s *updateServiceCacheStub) GetUpdateInfo(context.Context) (string, error) {
	if s.data == "" {
		return "", errors.New("cache miss")
	}
	return s.data, nil
}

func (s *updateServiceCacheStub) SetUpdateInfo(_ context.Context, data string, _ time.Duration) error {
	s.data = data
	return nil
}

type updateServiceGitHubClientStub struct {
	latestByRepo map[string]*GitHubRelease
	recentByRepo map[string][]*GitHubRelease
	recentErr    error
	downloadURLs []string
}

func (s *updateServiceGitHubClientStub) FetchLatestRelease(_ context.Context, repo string) (*GitHubRelease, error) {
	if release, ok := s.latestByRepo[repo]; ok {
		return release, nil
	}
	return nil, fmt.Errorf("unexpected latest release repository: %s", repo)
}

func (s *updateServiceGitHubClientStub) FetchRecentReleases(_ context.Context, repo string, _ int) ([]*GitHubRelease, error) {
	if s.recentErr != nil {
		return nil, s.recentErr
	}
	if releases, ok := s.recentByRepo[repo]; ok {
		return releases, nil
	}
	return nil, fmt.Errorf("unexpected recent release repository: %s", repo)
}

func (s *updateServiceGitHubClientStub) DownloadFile(_ context.Context, rawURL, _ string, _ int64) error {
	s.downloadURLs = append(s.downloadURLs, rawURL)
	return errUpdateDownloadStopped
}

func (s *updateServiceGitHubClientStub) FetchChecksumFile(context.Context, string) ([]byte, error) {
	panic("FetchChecksumFile should not be called when no update is available")
}

func TestUpdateServicePerformUpdateNoUpdateReturnsSentinel(t *testing.T) {
	svc := NewUpdateService(
		&updateServiceCacheStub{},
		&updateServiceGitHubClientStub{
			latestByRepo: map[string]*GitHubRelease{
				officialGithubRepo: {
					TagName: "v0.1.132",
					Name:    "v0.1.132",
				},
			},
		},
		"0.1.132",
		"release",
	)

	err := svc.PerformUpdate(context.Background())

	require.Error(t, err)
	require.True(t, errors.Is(err, ErrNoUpdateAvailable))
	require.ErrorIs(t, err, ErrNoUpdateAvailable)
}

func TestUpdateServicePerformUpdateUsesMatchingPatchedRelease(t *testing.T) {
	officialAsset := GitHubAsset{
		Name:               fmt.Sprintf("sub2api_0.1.133_%s_%s.tar.gz", runtime.GOOS, runtime.GOARCH),
		BrowserDownloadURL: "https://github.com/Wei-Shaw/sub2api/official.tar.gz",
	}
	patchedAsset := GitHubAsset{
		Name:               fmt.Sprintf("sub2api_0.1.133_%s_%s.tar.gz", runtime.GOOS, runtime.GOARCH),
		BrowserDownloadURL: "https://github.com/xin927706524-bot/sub2api-patched/patched.tar.gz",
	}
	client := &updateServiceGitHubClientStub{
		latestByRepo: map[string]*GitHubRelease{
			officialGithubRepo: {
				TagName: "v0.1.133",
				Assets:  []GitHubAsset{officialAsset},
			},
		},
		recentByRepo: map[string][]*GitHubRelease{
			patchedGithubRepo: {{
				TagName: "v0.1.133",
				Assets:  []GitHubAsset{patchedAsset},
			}},
		},
	}
	svc := NewUpdateService(&updateServiceCacheStub{}, client, "0.1.132", "release")

	err := svc.PerformUpdate(context.Background())

	require.ErrorIs(t, err, errUpdateDownloadStopped)
	require.Equal(t, []string{patchedAsset.BrowserDownloadURL}, client.downloadURLs)
}

func TestUpdateServicePerformUpdateRefusesOfficialFallback(t *testing.T) {
	officialAsset := GitHubAsset{
		Name:               fmt.Sprintf("sub2api_0.1.133_%s_%s.tar.gz", runtime.GOOS, runtime.GOARCH),
		BrowserDownloadURL: "https://github.com/Wei-Shaw/sub2api/official.tar.gz",
	}
	client := &updateServiceGitHubClientStub{
		latestByRepo: map[string]*GitHubRelease{
			officialGithubRepo: {
				TagName: "v0.1.133",
				Assets:  []GitHubAsset{officialAsset},
			},
		},
		recentByRepo: map[string][]*GitHubRelease{
			patchedGithubRepo: {{TagName: "v0.1.132"}},
		},
	}
	svc := NewUpdateService(&updateServiceCacheStub{}, client, "0.1.132", "release")

	err := svc.PerformUpdate(context.Background())

	require.Error(t, err)
	require.Contains(t, err.Error(), "refusing to install the official release")
	require.Empty(t, client.downloadURLs)
}

func newRollbackTestService(current string, releases []*GitHubRelease) *UpdateService {
	return NewUpdateService(
		&updateServiceCacheStub{},
		&updateServiceGitHubClientStub{
			recentByRepo: map[string][]*GitHubRelease{
				patchedGithubRepo: releases,
			},
		},
		current,
		"release",
	)
}

func TestUpdateServiceListRollbackVersionsFiltersAndCaps(t *testing.T) {
	releases := []*GitHubRelease{
		{TagName: "v0.1.148", PublishedAt: "2026-07-09T00:00:00Z"},                       // newer than current: excluded
		{TagName: "v0.1.147", PublishedAt: "2026-07-08T00:00:00Z"},                       // current: excluded
		{TagName: "v0.1.146-rc1", PublishedAt: "2026-07-07T12:00:00Z", Prerelease: true}, // prerelease: excluded
		{TagName: "v0.1.146", PublishedAt: "2026-07-07T00:00:00Z"},
		{TagName: "v0.1.145", PublishedAt: "2026-07-06T00:00:00Z", Draft: true}, // draft: excluded
		{TagName: "v0.1.144", PublishedAt: "2026-07-05T00:00:00Z"},
		{TagName: "v0.1.144", PublishedAt: "2026-07-05T00:00:00Z"}, // duplicate: excluded
		{TagName: "v0.1.143", PublishedAt: "2026-07-04T00:00:00Z"},
		{TagName: "v0.1.142", PublishedAt: "2026-07-03T00:00:00Z"}, // beyond cap of 3: excluded
	}
	svc := newRollbackTestService("0.1.147", releases)

	versions, err := svc.ListRollbackVersions(context.Background())

	require.NoError(t, err)
	require.Len(t, versions, 3)
	require.Equal(t, "0.1.146", versions[0].Version)
	require.Equal(t, "0.1.144", versions[1].Version)
	require.Equal(t, "0.1.143", versions[2].Version)
}

func TestUpdateServiceListRollbackVersionsSortsUnorderedInput(t *testing.T) {
	releases := []*GitHubRelease{
		{TagName: "v0.1.144"},
		{TagName: "v0.1.146"},
		{TagName: "v0.1.145"},
	}
	svc := newRollbackTestService("0.1.147", releases)

	versions, err := svc.ListRollbackVersions(context.Background())

	require.NoError(t, err)
	require.Len(t, versions, 3)
	require.Equal(t, "0.1.146", versions[0].Version)
	require.Equal(t, "0.1.145", versions[1].Version)
	require.Equal(t, "0.1.144", versions[2].Version)
}

func TestUpdateServiceListRollbackVersionsEmptyWhenNoneOlder(t *testing.T) {
	releases := []*GitHubRelease{
		{TagName: "v0.1.147"},
		{TagName: "v0.1.148"},
	}
	svc := newRollbackTestService("0.1.147", releases)

	versions, err := svc.ListRollbackVersions(context.Background())

	require.NoError(t, err)
	require.Empty(t, versions)
}

func TestUpdateServiceListRollbackVersionsPropagatesFetchError(t *testing.T) {
	svc := NewUpdateService(
		&updateServiceCacheStub{},
		&updateServiceGitHubClientStub{recentErr: errors.New("github unavailable")},
		"0.1.147",
		"release",
	)

	_, err := svc.ListRollbackVersions(context.Background())

	require.Error(t, err)
	require.Contains(t, err.Error(), "github unavailable")
}

func TestUpdateServiceRollbackToVersionRejectsDisallowedTargets(t *testing.T) {
	releases := []*GitHubRelease{
		{TagName: "v0.1.148"},
		{TagName: "v0.1.147"},
		{TagName: "v0.1.146"},
		{TagName: "v0.1.145"},
		{TagName: "v0.1.144"},
		{TagName: "v0.1.143"},
		{TagName: "v0.1.142"},
	}
	svc := newRollbackTestService("0.1.147", releases)

	for _, target := range []string{
		"",         // empty
		"0.1.147",  // current version
		"v0.1.147", // current version with prefix
		"0.1.148",  // newer than current
		"0.1.142",  // older than the 3 most recent
		"9.9.9",    // nonexistent
	} {
		err := svc.RollbackToVersion(context.Background(), target)
		require.ErrorIs(t, err, ErrRollbackVersionNotAllowed, "target %q should be rejected", target)
	}
}

func TestUpdateServiceRollbackToVersionAcceptsVPrefix(t *testing.T) {
	// No platform asset in the release: the target passes the allowlist check
	// and fails later at asset lookup, proving the version itself was accepted.
	releases := []*GitHubRelease{
		{TagName: "v0.1.147"},
		{TagName: "v0.1.146"},
	}
	svc := newRollbackTestService("0.1.147", releases)

	err := svc.RollbackToVersion(context.Background(), "v0.1.146")

	require.Error(t, err)
	require.NotErrorIs(t, err, ErrRollbackVersionNotAllowed)
	require.Contains(t, err.Error(), "no compatible release found")
}
