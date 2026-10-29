package config

import (
	"apple-store-helper/model"
	"encoding/json"
	"fmt"
	"testing"
)

// Match the fields consumed by services.Area.ProductsByCode.
type productSelection struct {
	DisplayValues struct {
		Colors map[string]json.RawMessage `json:"dimensionColor"`
	} `json:"displayValues"`
	Products []struct {
		Family   string `json:"familyType"`
		Code     string `json:"partNumber"`
		Color    string `json:"dimensionColor"`
		Capacity string `json:"dimensionCapacity"`
	} `json:"products"`
}

func TestNewIPhoneCatalogs(t *testing.T) {
	for _, area := range model.Areas {
		t.Run(area.Locale, func(t *testing.T) {
			data, err := ReadConfigFile(fmt.Sprintf("products_%s.json", area.Locale))
			if err != nil {
				t.Fatal(err)
			}
			var selections []productSelection
			if err := json.Unmarshal(data, &selections); err != nil {
				t.Fatal(err)
			}
			counts := map[string]int{}
			codes := map[string]bool{}
			titles := map[string]bool{}
			for _, selection := range selections {
				for _, product := range selection.Products {
					counts[product.Family]++
					switch product.Family {
					case "iphone18pro", "iphone18promax", "iphoneduo":
					default:
						t.Errorf("unsupported family in selector: %s", product.Family)
						continue
					}
					var finish struct {
						Value string `json:"value"`
					}
					if err := json.Unmarshal(selection.DisplayValues.Colors[product.Color], &finish); err != nil {
						t.Fatalf("%s color: %v", product.Code, err)
					}
					color := finish.Value
					if product.Code == "" || color == "" || product.Capacity == "" {
						t.Fatalf("incomplete product: %+v", product)
					}
					switch product.Capacity {
					case "256gb", "512gb", "1tb", "2tb":
					default:
						t.Errorf("unexpected capacity: %+v", product)
					}
					title := fmt.Sprintf("%s - %s - %s", product.Family, color, product.Capacity)
					if codes[product.Code] || titles[title] {
						t.Errorf("duplicate SKU or selector title: %s (%s)", product.Code, title)
					}
					codes[product.Code], titles[title] = true, true
				}
			}
			for family, want := range map[string]int{
				"iphone18pro": 16, "iphone18promax": 16, "iphoneduo": 8,
			} {
				if counts[family] != want {
					t.Errorf("%s: got %d variants, want %d", family, counts[family], want)
				}
			}
		})
	}
}
