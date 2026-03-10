package handler

import (
	"context"
	"errors"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgconn"
	"golang.org/x/crypto/bcrypt"

	"github.com/embedai/datahub/gateway/internal/middleware"
	"github.com/embedai/datahub/gateway/internal/repo"
)

type UserRepo interface {
	FindByEmail(ctx context.Context, email string) (*repo.User, error)
	Create(ctx context.Context, u *repo.User) error
}

type AuthHandler struct {
	userRepo    UserRepo
	jwtSecret   string
	expireHours int
}

func NewAuthHandler(userRepo UserRepo, jwtSecret string, expireHours int) *AuthHandler {
	return &AuthHandler{
		userRepo:    userRepo,
		jwtSecret:   jwtSecret,
		expireHours: expireHours,
	}
}

// POST /auth/login
// Body: { email, password }
// Response: { token, user }
func (h *AuthHandler) Login(c *gin.Context) {
	var req struct {
		Email    string `json:"email" binding:"required,email"`
		Password string `json:"password" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	user, err := h.userRepo.FindByEmail(c.Request.Context(), req.Email)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "invalid credentials"})
		return
	}

	if err := bcrypt.CompareHashAndPassword([]byte(user.HashedPassword), []byte(req.Password)); err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "invalid credentials"})
		return
	}

	token, err := h.generateJWT(user)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to generate token"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"token": token,
		"user": gin.H{
			"id":         user.ID,
			"email":      user.Email,
			"name":       user.Name,
			"role":       user.Role,
			"project_id": user.ProjectID,
		},
	})
}

// POST /auth/register  (admin only via internal use or first-boot)
func (h *AuthHandler) Register(c *gin.Context) {
	var req struct {
		Email     string `json:"email" binding:"required,email"`
		Password  string `json:"password" binding:"required,min=8"`
		Name      string `json:"name" binding:"required"`
		Role      string `json:"role" binding:"required,oneof=admin engineer annotator_internal annotator_outsource"`
		ProjectID string `json:"project_id"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	hashed, err := bcrypt.GenerateFromPassword([]byte(req.Password), bcrypt.DefaultCost)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to hash password"})
		return
	}

	user := &repo.User{
		ID:             uuid.New().String(),
		Email:          req.Email,
		Name:           req.Name,
		HashedPassword: string(hashed),
		Role:           req.Role,
		ProjectID:      req.ProjectID,
	}

	if err := h.userRepo.Create(c.Request.Context(), user); err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) {
			switch pgErr.Code {
			case "23505": // unique_violation
				c.JSON(http.StatusConflict, gin.H{"error": "email already exists"})
			case "23503": // foreign_key_violation
				c.JSON(http.StatusUnprocessableEntity, gin.H{"error": "project_id does not exist"})
			default:
				c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to create user"})
			}
		} else {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to create user"})
		}
		return
	}

	c.JSON(http.StatusCreated, gin.H{
		"id":         user.ID,
		"email":      user.Email,
		"name":       user.Name,
		"role":       user.Role,
		"project_id": user.ProjectID,
	})
}

func (h *AuthHandler) generateJWT(user *repo.User) (string, error) {
	claims := middleware.Claims{
		UserID:    user.ID,
		ProjectID: user.ProjectID,
		Role:      user.Role,
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Duration(h.expireHours) * time.Hour)),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
		},
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString([]byte(h.jwtSecret))
}
