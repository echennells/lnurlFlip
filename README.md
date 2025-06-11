# LnurlFlip - An [LNbits](https://github.com/lnbits/lnbits) Extension

## Overview

LnurlFlip creates a single LNURL that intelligently switches between payment and withdrawal modes based on the current balance. Share one QR code that can both receive payments when empty and allow withdrawals when funded.

## How It Works

- **Payment Mode**: When balance is below 50 sats, shows payment interface
- **Withdrawal Mode**: When balance is sufficient, shows withdrawal interface  
- **Automatic Switching**: Mode changes dynamically based on real-time balance

## Features

- ✨ Single QR code for both payments and withdrawals
- 💬 Comment support for payments
- 📊 Transaction history and usage stats

## Installation

### From Extension Manifest
1. In LNbits, go to **Server** → **Extensions** → **Extension Sources**
2. Add: `https://raw.githubusercontent.com/echennells/lnurlFlip/main/manifest.json`
3. Enable the LnurlFlip extension

## Setup

### Step 1: Create Required Links
Before creating a flip link, you need:

1. **LNURL Pay link** (from LNURLp extension)
   - Set your desired payment amount range
   
2. **LNURL Withdraw link** (from Withdraw extension)  
   - Set minimum and maximum withdrawal amounts

### Step 2: Create Your Flip Link
1. Go to LnurlFlip extension
2. Click **"New LnurlFlip"**
3. Enter a name and select your wallet
4. Choose your existing pay and withdraw links
5. Click **"Create LnurlFlip"**

### Step 3: Share Your Link
1. Click the QR code icon next to your flip link
2. Share the QR code or LNURL string
3. The link automatically switches between payment and withdrawal modes
