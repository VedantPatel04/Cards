I am going to keep my documentation concise and easy to understand. 
Therefore I will keep my daily documentation to a maximum of 5 things:

# **CONTEXT OF THE PROBLEM**
----------------------------
 - Create an organized directory structure as a foundation for the rest of the project
 - Set up django and django rest framework
 - Install and setup token creation with SimpleJWT
 - Create a 'ping' endpoint to ensure token access works

## **OVERVIEW OF CHANGES MADE**
-------------------------------

### ***Create an organized directory structure for the project:***

- `Cards/backend/` as Django root
- `backend/apps/` contains five domain apps (`users`, `cards`, `uploads`, `transactions`, `recommendations`)
- `backend/services/` contains business logic scripts
- `backend/data/` stores card catalog snapshots and uploaded statements
- `backend/config/` holds project-wide settings see [settings-architecture.md](docs/settings-architecture.md)

### ***Set up Django and Django REST Framework***
- .venv setup
- installed dependencies, see [requirements.txt](backend/requirements.txt)
  
### ***Install SimpleJWT, setup Token Access:***
- registered in INSTALLED_APPS
- added to DEFAULT_AUTHENTICATION_CLASSES
- Wired up TokenObtainPairView, and TokenRefreshView, and TokenVerifyViews to urls
### ***Auth Verification endpoint:***
- verify authentication of user with `isAuthenticated` endpoint


# **DECISIONS MADE**
--------------------
### SimpleJWT vs. TokenAuthentication?
**Why I chose SimpleJWT instead of TokenAuth**
- SimpleJWT is stateless, meaning the DB doesn't store the token and this saves DB lookup and this is beneficial if I scale this program to a larger audience
- gives me a chance to work with non-native Django functionality
- 
**Tradeoffs**
- simplejwt is not native to Django meaning I have to manage extra dependencies if I want to build on top of it
# **RESULTS OF DECISIONS**
--------------------------
- Running API with protected endpoints verified in Postman 
- Settings split means local dev and test environments are fully isolated from day one

# **THINGS TO REMEMBER**
------------------------
- `access` token expires in 5 min — At the moment, must use a newly created access token, since interceptor + refresh token functionality not set-up
- `AUTH_USER_MODEL` must be set before the first migration — changing it after could be a hassle