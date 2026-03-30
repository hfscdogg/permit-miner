# PURL Landing Page: Elementor Setup Guide

## Overview

The PURL (Personalized URL) landing page lives at `getlivewire.com/welcome`. It's a single WordPress page that dynamically adjusts content based on the permit type passed in the URL. Every postcard QR code links here with a unique `pid` parameter.

## Step-by-Step Setup

### 1. Create the WordPress Page

1. In WordPress admin, create a new page titled "Welcome" with slug `welcome`
2. Set the page template to "Elementor Full Width" (no sidebar)
3. Open in Elementor editor

### 2. Build the Page Layout

Create these sections top to bottom:

**Section 1: Hero**
- Full-width section with dark navy background (`#1a2744` or match site header)
- Livewire logo (use site logo widget or image)
- Heading widget with ID `purl-headline` — default text: "Your Home Deserves the Best Technology"
  - To set the ID: click the heading → Advanced tab → CSS ID → enter `purl-headline`
- Text widget with ID `purl-subheadline` — default text: "Smart home design, installation, and support."

**Section 2: Personalized Content** (ID: `purl-personalized`)
- Set section CSS ID to `purl-personalized`
- In Advanced → Custom CSS, add: `#purl-personalized { display: block; }` (the JS will show it after loading)
- Text Editor widget with ID `purl-body` — default body copy about Livewire services
- Two-column layout:
  - Left: Body text
  - Right: Project photo or smart home lifestyle image

**Section 3: CTA**
- Primary button: "Book a Complimentary Consultation"
  - Link to Zoho Bookings URL: `https://livewire.zohobookings.com/#/customer/[your-booking-page]`
  - Style: Orange background (`#e8943a`), white text, large padding
- Secondary: "Call Us" button
  - Link: `tel:8049379001`
  - Text: "(804) 937-9001"
  - Style: Outlined, dark navy border

**Section 4: Social Proof**
- Testimonial or project gallery (1-2 photos)
- "Serving Richmond Since 2003" tagline
- Optional: badges/certifications

**Section 5: Footer**
- Standard site footer

### 3. Add the JavaScript

**Option A: Elementor HTML Widget (simplest)**
1. Add an HTML widget at the bottom of the page (inside the footer section or after the CTA)
2. Paste the contents of `purl_script.js` wrapped in `<script>` tags:

```html
<script>
// Paste the entire contents of purl_script.js here
</script>
```

**Option B: Code Snippets Plugin (cleaner)**
1. Install the "Code Snippets" plugin if not already active
2. Create a new snippet, set it to run only on the "welcome" page
3. Paste `purl_script.js` content
4. Enable the snippet

**Option C: Theme functions.php**
1. Upload `purl_script.js` to your theme's js directory
2. Add to functions.php:
```php
function permit_miner_purl_script() {
    if (is_page('welcome')) {
        wp_enqueue_script('purl-script', get_template_directory_uri() . '/js/purl_script.js', array(), '1.0', true);
    }
}
add_action('wp_enqueue_scripts', 'permit_miner_purl_script');
```

### 4. Update the Webhook URL

In `purl_script.js`, update the `WEBHOOK_URL` variable to match the actual Zoho Creator REST API endpoint URL after the Creator function is deployed.

The format is typically:
```
https://creatorapp.zoho.com/api/v2/[owner]/permit-miner/report/Scan_Webhook
```

### 5. Configure Google Analytics UTM Tracking

The postcard QR URLs include UTM parameters:
- `utm_source=permit_miner`
- `utm_medium=direct_mail`
- `utm_campaign=luxury_permits` (or `luxury_permits_drip` for second touch)
- `utm_content={permit_record_id}`

Google Analytics will automatically capture these. No additional GA setup needed beyond having the GA tracking code active on the site.

To view in GA:
- Acquisition > Campaigns > All Campaigns > "luxury_permits"
- Or create a custom segment filtering on utm_source = "permit_miner"

### 6. Test

1. Open `getlivewire.com/welcome?pid=test123` in a browser
2. Verify the page loads with default content
3. Check browser console for any JS errors
4. Once the Zoho Creator webhook is live, test with a real permit record ID
5. Verify:
   - Page headline changes based on permit type returned
   - Zoho Creator record updates to "Engaged"
   - Sales team receives scan alert email

### Important Notes

- The page should work fine without a `pid` parameter (shows default content, no webhook fires)
- The webhook call is fire-and-forget from the browser's perspective — page content shows immediately, the webhook fires in the background
- CORS: The Zoho Creator REST API function must allow cross-origin requests from getlivewire.com. Configure this in Creator's API settings.
- Mobile: Test on iPhone since most QR scans will come from mobile cameras
