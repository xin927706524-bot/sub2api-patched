package service

import "testing"

func TestGroupPublicRateMultiplier(t *testing.T) {
	t.Run("falls back to billing rate", func(t *testing.T) {
		group := &Group{RateMultiplier: 0.65}
		if got := group.PublicRateMultiplier(); got != 0.65 {
			t.Fatalf("PublicRateMultiplier() = %v, want 0.65", got)
		}
	})

	t.Run("uses display override", func(t *testing.T) {
		displayRate := 1.2
		group := &Group{RateMultiplier: 0.65, DisplayRateMultiplier: &displayRate}
		if got := group.PublicRateMultiplier(); got != 1.2 {
			t.Fatalf("PublicRateMultiplier() = %v, want 1.2", got)
		}
		if group.RateMultiplier != 0.65 {
			t.Fatalf("billing rate changed to %v", group.RateMultiplier)
		}
	})
}

func TestGroupPublicTokenMultiplier(t *testing.T) {
	t.Run("defaults to one", func(t *testing.T) {
		if got := (&Group{}).PublicTokenMultiplier(); got != 1 {
			t.Fatalf("PublicTokenMultiplier() = %v, want 1", got)
		}
	})

	t.Run("uses display token override", func(t *testing.T) {
		displayTokens := 1.2
		group := &Group{DisplayTokenMultiplier: &displayTokens}
		if got := group.PublicTokenMultiplier(); got != 1.2 {
			t.Fatalf("PublicTokenMultiplier() = %v, want 1.2", got)
		}
	})
}
