package dto

import (
	"encoding/json"
	"testing"

	"github.com/Wei-Shaw/sub2api/internal/service"
)

func TestGroupDisplayRateVisibility(t *testing.T) {
	displayRate := 1.2
	displayTokens := 1.3
	group := &service.Group{
		ID:                     1,
		RateMultiplier:         0.65,
		DisplayRateMultiplier:  &displayRate,
		DisplayTokenMultiplier: &displayTokens,
	}

	userDTO := GroupFromService(group)
	if userDTO.RateMultiplier != displayRate {
		t.Fatalf("user rate_multiplier = %v, want %v", userDTO.RateMultiplier, displayRate)
	}
	userJSON, err := json.Marshal(userDTO)
	if err != nil {
		t.Fatal(err)
	}
	var userFields map[string]any
	if err := json.Unmarshal(userJSON, &userFields); err != nil {
		t.Fatal(err)
	}
	if _, ok := userFields["display_rate_multiplier"]; ok {
		t.Fatal("user DTO must not expose display_rate_multiplier separately")
	}
	if _, ok := userFields["display_token_multiplier"]; ok {
		t.Fatal("user DTO must not expose display_token_multiplier")
	}

	adminDTO := GroupFromServiceAdmin(group)
	if adminDTO.RateMultiplier != 0.65 {
		t.Fatalf("admin rate_multiplier = %v, want 0.65", adminDTO.RateMultiplier)
	}
	if adminDTO.DisplayRateMultiplier == nil || *adminDTO.DisplayRateMultiplier != displayRate {
		t.Fatalf("admin display_rate_multiplier = %v, want %v", adminDTO.DisplayRateMultiplier, displayRate)
	}
	if adminDTO.DisplayTokenMultiplier == nil || *adminDTO.DisplayTokenMultiplier != displayTokens {
		t.Fatalf("admin display_token_multiplier = %v, want %v", adminDTO.DisplayTokenMultiplier, displayTokens)
	}
}
