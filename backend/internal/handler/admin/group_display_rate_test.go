package admin

import (
	"encoding/json"
	"testing"
)

func TestUpdateGroupRequestDisplayRateTriState(t *testing.T) {
	tests := []struct {
		name      string
		payload   string
		wantSet   bool
		wantValue *float64
	}{
		{name: "omitted", payload: `{}`},
		{name: "cleared", payload: `{"display_rate_multiplier":null}`, wantSet: true},
		{name: "set", payload: `{"display_rate_multiplier":1.2}`, wantSet: true, wantValue: float64Pointer(1.2)},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var req UpdateGroupRequest
			if err := json.Unmarshal([]byte(tt.payload), &req); err != nil {
				t.Fatal(err)
			}
			value, set := req.DisplayRateMultiplier.ToServiceInput()
			if set != tt.wantSet {
				t.Fatalf("set = %v, want %v", set, tt.wantSet)
			}
			if tt.wantValue == nil {
				if value != nil {
					t.Fatalf("value = %v, want nil", *value)
				}
				return
			}
			if value == nil || *value != *tt.wantValue {
				t.Fatalf("value = %v, want %v", value, *tt.wantValue)
			}
		})
	}
}

func TestUpdateGroupRequestDisplayTokenTriState(t *testing.T) {
	tests := []struct {
		name      string
		payload   string
		wantSet   bool
		wantValue *float64
	}{
		{name: "omitted", payload: `{}`},
		{name: "cleared", payload: `{"display_token_multiplier":null}`, wantSet: true},
		{name: "set", payload: `{"display_token_multiplier":1.2}`, wantSet: true, wantValue: float64Pointer(1.2)},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var req UpdateGroupRequest
			if err := json.Unmarshal([]byte(tt.payload), &req); err != nil {
				t.Fatal(err)
			}
			value, set := req.DisplayTokenMultiplier.ToServiceInput()
			if set != tt.wantSet {
				t.Fatalf("set = %v, want %v", set, tt.wantSet)
			}
			if tt.wantValue == nil {
				if value != nil {
					t.Fatalf("value = %v, want nil", *value)
				}
				return
			}
			if value == nil || *value != *tt.wantValue {
				t.Fatalf("value = %v, want %v", value, *tt.wantValue)
			}
		})
	}
}

func float64Pointer(value float64) *float64 { return &value }
