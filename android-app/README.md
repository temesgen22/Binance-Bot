# Binance Bot Mobile App

Android mobile application for the Binance Trading Bot.

## 🏗️ Architecture

- **MVVM + Clean Architecture**
- **Jetpack Compose** for UI
- **Hilt** for Dependency Injection
- **Room** for local database
- **Retrofit** for API calls
- **Coroutines + Flow** for async operations

## 📁 Project Structure

```
app/src/main/java/com/binancebot/mobile/
├── app/                          # Application class
├── data/
│   ├── local/                   # Room database, DataStore
│   │   ├── database/
│   │   ├── dao/
│   │   └── entities/
│   ├── remote/                   # API services, DTOs
│   │   ├── api/
│   │   ├── dto/
│   │   └── websocket/
│   └── repository/              # Repository implementations
├── domain/
│   ├── model/                    # Domain models
│   ├── usecase/                  # Business logic
│   └── repository/               # Repository interfaces
├── presentation/
│   ├── theme/                    # Material Design theme
│   ├── navigation/               # Navigation setup
│   ├── screens/                  # Composable screens
│   │   ├── auth/
│   │   ├── dashboard/
│   │   ├── strategies/
│   │   ├── trades/
│   │   ├── accounts/
│   │   └── settings/
│   ├── components/               # Reusable UI components
│   │   ├── charts/
│   │   ├── cards/
│   │   └── dialogs/
│   └── viewmodel/                # ViewModels
├── di/                           # Dependency injection modules
└── util/                         # Utilities, extensions
```

## 🚀 Getting Started

### Prerequisites

- Android Studio Hedgehog (2023.1.1) or later
- JDK 17 or later
- Android SDK 26+ (minimum)
- Android SDK 34 (target)

### Setup

1. Open the project in Android Studio
2. Sync Gradle files
3. Build the project
4. Run on emulator or device

### Configuration

Before running, configure the API base URL in:
- `di/NetworkModule.kt` (to be created)

## 📱 Features

- ✅ Authentication (Login/Register)
- ✅ Dashboard
- ✅ Strategy Management
- ✅ Trade Tracking
- ✅ Account Management
- ✅ Real-time Updates (polling)
- ✅ Offline Support
- ✅ Dark Mode

## 🛠️ Development

### Building

```bash
./gradlew assembleDebug
```

### Testing

```bash
./gradlew test
./gradlew connectedAndroidTest
```

## 📚 Documentation

See the main project's `ANDROID_APP_DESIGN_PLAN.md` for complete implementation details.

## 🔗 Backend API

The app connects to the FastAPI backend. Ensure the backend is running and accessible.

Base URL: `http://your-backend-url/api`

## 📄 License

Same as main project.


































