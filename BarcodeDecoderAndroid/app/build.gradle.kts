import java.io.FileInputStream
import java.io.FileOutputStream
import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val (appVersionCode, appVersionName) = run {
    val versionPropsFile = rootProject.file("version.properties")
    val versionProps = Properties()
    if (versionPropsFile.exists()) {
        FileInputStream(versionPropsFile).use { versionProps.load(it) }
    }

    val major = versionProps.getProperty("major", "1").toInt()
    var minor = versionProps.getProperty("minor", "1").toInt()
    var vCode = versionProps.getProperty("versionCode", "1").toInt()

    val isAssembleTask = gradle.startParameter.taskNames.any {
        it.contains("assemble", ignoreCase = true) || it.contains("bundle", ignoreCase = true)
    }

    if (isAssembleTask) {
        minor += 1
        vCode += 1
        versionProps["major"] = major.toString()
        versionProps["minor"] = minor.toString()
        versionProps["versionCode"] = vCode.toString()
        FileOutputStream(versionPropsFile).use {
            versionProps.store(it, "Auto-incremented build version")
        }
    }

    Pair(vCode, "$major.$minor")
}

android {
    namespace = "com.barcodedecoder"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.barcodedecoder"
        minSdk = 24
        targetSdk = 34
        versionCode = appVersionCode
        versionName = appVersionName

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        vectorDrawables {
            useSupportLibrary = true
        }
    }

    signingConfigs {
        create("release") {
            storeFile = file("${rootProject.projectDir}/release-key.jks")
            storePassword = "-+iBr)MWJbzP72cTq#jL"
            keyAlias = "barcodedecoder"
            keyPassword = "-+iBr)MWJbzP72cTq#jL"
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
        debug {
            applicationIdSuffix = ".debug"
            isDebuggable = true
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_1_8
        targetCompatibility = JavaVersion.VERSION_1_8
    }

    kotlinOptions {
        jvmTarget = "1.8"
    }

    buildFeatures {
        viewBinding = true
    }

    applicationVariants.all {
        if (buildType.name == "release") {
            outputs.all {
                val output = this as? com.android.build.gradle.internal.api.BaseVariantOutputImpl
                output?.outputFileName = "BarcodeDecoderForSmdResistorsAndCondensators_kean5782.apk"
            }
        }
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("com.google.android.material:material:1.11.0")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.7.0")

    // CameraX
    val cameraxVersion = "1.3.1"
    implementation("androidx.camera:camera-core:$cameraxVersion")
    implementation("androidx.camera:camera-camera2:$cameraxVersion")
    implementation("androidx.camera:camera-lifecycle:$cameraxVersion")
    implementation("androidx.camera:camera-view:$cameraxVersion")

    // Google ML Kit Barcode Scanning
    implementation("com.google.mlkit:barcode-scanning:17.2.0")

    // Coroutines
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")

    // Unit tests
    testImplementation("junit:junit:4.13.2")
}
