package main

import (
	"testing"

	"github.com/cloudwego/kitex/pkg/kerrors"
)

func TestSyntheticBizErrorClassification(t *testing.T) {
	err := kerrors.NewBizStatusError(2101, "synthetic handler error")
	biz, ok := kerrors.FromBizStatusError(err)
	if !ok || biz.BizStatusCode() != 2101 {
		t.Fatalf("Kitex did not expose actual biz error code: %v", err)
	}
}
