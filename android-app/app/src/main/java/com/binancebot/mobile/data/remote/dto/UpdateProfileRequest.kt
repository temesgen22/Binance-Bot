package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

data class UpdateProfileRequest(
    @SerializedName("username") val username: String,
    @SerializedName("email") val email: String
)
