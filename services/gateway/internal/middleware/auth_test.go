package middleware_test

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/embedai/datahub/gateway/internal/middleware"
)

func init() {
	gin.SetMode(gin.TestMode)
}

func makeToken(secret, userID, role, projectID string) string {
	claims := middleware.Claims{
		UserID:    userID,
		ProjectID: projectID,
		Role:      role,
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
		},
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	signed, _ := token.SignedString([]byte(secret))
	return signed
}

func TestAuth_MissingToken(t *testing.T) {
	w := httptest.NewRecorder()
	_, r := gin.CreateTestContext(w)
	r.GET("/test", middleware.Auth("secret"), func(c *gin.Context) { c.Status(200) })
	req, _ := http.NewRequest("GET", "/test", nil)
	r.ServeHTTP(w, req)
	if w.Code != 401 {
		t.Errorf("expected 401, got %d", w.Code)
	}
}

func TestAuth_InvalidToken(t *testing.T) {
	w := httptest.NewRecorder()
	_, r := gin.CreateTestContext(w)
	r.GET("/test", middleware.Auth("secret"), func(c *gin.Context) { c.Status(200) })
	req, _ := http.NewRequest("GET", "/test", nil)
	req.Header.Set("Authorization", "Bearer invalid.token.here")
	r.ServeHTTP(w, req)
	if w.Code != 401 {
		t.Errorf("expected 401, got %d", w.Code)
	}
}

func TestAuth_ValidToken(t *testing.T) {
	const secret = "test-secret"
	token := makeToken(secret, "user-1", "admin", "proj-1")

	w := httptest.NewRecorder()
	_, r := gin.CreateTestContext(w)
	r.GET("/test", middleware.Auth(secret), func(c *gin.Context) {
		userID := c.GetString("user_id")
		if userID != "user-1" {
			t.Errorf("expected user_id=user-1, got %s", userID)
		}
		c.Status(200)
	})
	req, _ := http.NewRequest("GET", "/test", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	r.ServeHTTP(w, req)
	if w.Code != 200 {
		t.Errorf("expected 200, got %d", w.Code)
	}
}

func TestRequireRole_Allowed(t *testing.T) {
	const secret = "test-secret"
	token := makeToken(secret, "user-1", "admin", "proj-1")

	w := httptest.NewRecorder()
	_, r := gin.CreateTestContext(w)
	r.GET("/test", middleware.Auth(secret), middleware.RequireRole("admin", "engineer"), func(c *gin.Context) {
		c.Status(200)
	})
	req, _ := http.NewRequest("GET", "/test", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	r.ServeHTTP(w, req)
	if w.Code != 200 {
		t.Errorf("expected 200, got %d", w.Code)
	}
}

func TestRequireRole_Forbidden(t *testing.T) {
	const secret = "test-secret"
	token := makeToken(secret, "user-1", "annotator_internal", "proj-1")

	w := httptest.NewRecorder()
	_, r := gin.CreateTestContext(w)
	r.GET("/test", middleware.Auth(secret), middleware.RequireRole("admin"), func(c *gin.Context) {
		c.Status(200)
	})
	req, _ := http.NewRequest("GET", "/test", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	r.ServeHTTP(w, req)
	if w.Code != 403 {
		t.Errorf("expected 403, got %d", w.Code)
	}
}
