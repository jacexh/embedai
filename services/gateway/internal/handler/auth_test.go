package handler_test

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"golang.org/x/crypto/bcrypt"

	"github.com/embedai/datahub/gateway/internal/handler"
	"github.com/embedai/datahub/gateway/internal/repo"
)

func init() {
	gin.SetMode(gin.TestMode)
}

// stubUserRepo is an in-memory stub for testing.
type stubUserRepo struct {
	users map[string]*repo.User
}

func newStubUserRepo() *stubUserRepo {
	return &stubUserRepo{users: make(map[string]*repo.User)}
}

func (s *stubUserRepo) FindByEmail(_ context.Context, email string) (*repo.User, error) {
	u, ok := s.users[email]
	if !ok {
		return nil, http.ErrNoCookie // sentinel error
	}
	return u, nil
}

func (s *stubUserRepo) Create(_ context.Context, u *repo.User) error {
	if _, exists := s.users[u.Email]; exists {
		return http.ErrNoCookie
	}
	s.users[u.Email] = u
	return nil
}

func postJSON(t *testing.T, router *gin.Engine, path string, body any) *httptest.ResponseRecorder {
	t.Helper()
	data, _ := json.Marshal(body)
	w := httptest.NewRecorder()
	req, _ := http.NewRequest("POST", path, bytes.NewReader(data))
	req.Header.Set("Content-Type", "application/json")
	router.ServeHTTP(w, req)
	return w
}

func setupRouter(userRepo handler.UserRepo) *gin.Engine {
	r := gin.New()
	h := handler.NewAuthHandler(userRepo, "test-secret", 24)
	r.POST("/auth/login", h.Login)
	r.POST("/auth/register", h.Register)
	return r
}

func TestLogin_InvalidCredentials_UnknownEmail(t *testing.T) {
	stub := newStubUserRepo()
	r := setupRouter(stub)

	w := postJSON(t, r, "/auth/login", map[string]string{
		"email": "notfound@example.com", "password": "password123",
	})
	if w.Code != 401 {
		t.Errorf("expected 401, got %d", w.Code)
	}
}

func TestLogin_InvalidCredentials_WrongPassword(t *testing.T) {
	stub := newStubUserRepo()
	hashed, _ := bcrypt.GenerateFromPassword([]byte("correct-pass"), bcrypt.DefaultCost)
	stub.users["user@example.com"] = &repo.User{
		ID: "u1", Email: "user@example.com", HashedPassword: string(hashed), Role: "engineer",
	}
	r := setupRouter(stub)

	w := postJSON(t, r, "/auth/login", map[string]string{
		"email": "user@example.com", "password": "wrong-pass",
	})
	if w.Code != 401 {
		t.Errorf("expected 401, got %d", w.Code)
	}
}

func TestLogin_Success(t *testing.T) {
	stub := newStubUserRepo()
	hashed, _ := bcrypt.GenerateFromPassword([]byte("correct-pass"), bcrypt.DefaultCost)
	stub.users["user@example.com"] = &repo.User{
		ID: "u1", Email: "user@example.com", Name: "Test User",
		HashedPassword: string(hashed), Role: "engineer",
	}
	r := setupRouter(stub)

	w := postJSON(t, r, "/auth/login", map[string]string{
		"email": "user@example.com", "password": "correct-pass",
	})
	if w.Code != 200 {
		t.Errorf("expected 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp map[string]any
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp["token"] == nil || resp["token"] == "" {
		t.Error("expected non-empty token in response")
	}
}

func TestRegister_Success(t *testing.T) {
	stub := newStubUserRepo()
	r := setupRouter(stub)

	w := postJSON(t, r, "/auth/register", map[string]string{
		"email": "new@example.com", "password": "password123",
		"name": "New User", "role": "annotator_internal",
	})
	if w.Code != 201 {
		t.Errorf("expected 201, got %d: %s", w.Code, w.Body.String())
	}
}

func TestLogin_BadRequest_MissingFields(t *testing.T) {
	stub := newStubUserRepo()
	r := setupRouter(stub)

	w := postJSON(t, r, "/auth/login", map[string]string{"email": "only@example.com"})
	if w.Code != 400 {
		t.Errorf("expected 400, got %d", w.Code)
	}
}
