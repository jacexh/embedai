package repo

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

type User struct {
	ID             string
	Email          string
	Name           string
	HashedPassword string
	Role           string
	ProjectID      string
	SkillTags      []string
}

type UserRepo struct {
	db *pgxpool.Pool
}

func NewUserRepo(db *pgxpool.Pool) *UserRepo {
	return &UserRepo{db: db}
}

func (r *UserRepo) FindByEmail(ctx context.Context, email string) (*User, error) {
	u := &User{}
	var projectID *string
	err := r.db.QueryRow(ctx,
		`SELECT id, email, name, hashed_password, role, project_id
		 FROM users WHERE email=$1 AND is_active=true`,
		email,
	).Scan(&u.ID, &u.Email, &u.Name, &u.HashedPassword, &u.Role, &projectID)
	if err != nil {
		return nil, err
	}
	if projectID != nil {
		u.ProjectID = *projectID
	}
	return u, nil
}

func (r *UserRepo) Create(ctx context.Context, u *User) error {
	_, err := r.db.Exec(ctx,
		`INSERT INTO users (id, email, name, hashed_password, role, project_id)
		 VALUES ($1, $2, $3, $4, $5, NULLIF($6, ''))`,
		u.ID, u.Email, u.Name, u.HashedPassword, u.Role, u.ProjectID,
	)
	return err
}
