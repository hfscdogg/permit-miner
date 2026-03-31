/**
 * PERMIT MINER: PURL Landing Page Script
 *
 * Drop this into the WordPress/Elementor page at getlivewire.com/welcome
 * Reads the permit ID from the URL, fires the scan webhook, and
 * dynamically adjusts page content based on permit type.
 *
 * Usage: Add as a Custom HTML widget in Elementor, or enqueue via
 * functions.php / Code Snippets plugin.
 */

(function () {
  'use strict';

  // --- CONFIG ---
  // WordPress endpoint on getlivewire.com (registered by permit-miner.php mu-plugin)
  var WEBHOOK_URL = 'https://getlivewire.com/permit-scan';

  // --- READ PID FROM URL ---
  var params = new URLSearchParams(window.location.search);
  var pid = params.get('pid');

  if (!pid) {
    // No permit ID - show default content, don't fire webhook
    return;
  }

  // --- FIRE SCAN WEBHOOK ---
  fetch(WEBHOOK_URL + '?pid=' + encodeURIComponent(pid), {
    method: 'GET',
    mode: 'cors'
  })
    .then(function (response) { return response.json(); })
    .then(function (data) {
      if (data.status === 'ok') {
        updatePageContent(data);
      }
    })
    .catch(function (err) {
      // Webhook failure should not break the page experience
      console.log('Permit Miner: webhook error', err);
    });

  // --- DYNAMIC CONTENT SWAP ---
  function updatePageContent(data) {
    var headline = document.getElementById('purl-headline');
    var subheadline = document.getElementById('purl-subheadline');
    var bodyText = document.getElementById('purl-body');

    if (!headline) return;

    var tags = (data.permit_tags || '').toLowerCase();
    var type = (data.permit_type || '').toLowerCase();
    var isNew = data.is_new_construction;

    // Determine content variant
    var content = getContentByPermitType(tags, type, isNew);

    headline.textContent = content.headline;
    if (subheadline) subheadline.textContent = content.subheadline;
    if (bodyText) bodyText.innerHTML = content.body;

    // Show the personalized section (hidden by default in Elementor)
    var personalSection = document.getElementById('purl-personalized');
    if (personalSection) {
      personalSection.style.display = 'block';
    }
  }

  function getContentByPermitType(tags, type, isNew) {
    // New Construction
    if (isNew || tags.indexOf('new_construction') !== -1 || type.indexOf('new') !== -1) {
      return {
        headline: 'Congratulations on Your New Home',
        subheadline: 'Make it smart from day one.',
        body: '<p>Building a new home is the perfect time to integrate technology seamlessly into every room. From whole-home networking and distributed audio to motorized shading and security, Livewire designs systems that work together beautifully — and last for decades.</p><p>We work directly with your builder to ensure everything is wired, programmed, and ready before you move in.</p>'
      };
    }

    // Pool
    if (tags.indexOf('pool') !== -1) {
      return {
        headline: 'Your New Pool Deserves a Soundtrack',
        subheadline: 'Outdoor audio, lighting, and automation — designed for your space.',
        body: '<p>A luxury pool project is the perfect opportunity to add weatherproof speakers, landscape lighting control, pool automation, and outdoor surveillance. Livewire designs outdoor technology that looks invisible and sounds incredible.</p>'
      };
    }

    // Deck / Outdoor Living
    if (type.indexOf('deck') !== -1 || type.indexOf('outdoor') !== -1 || type.indexOf('patio') !== -1) {
      return {
        headline: 'Bring Your Outdoor Living Space to Life',
        subheadline: 'Audio, lighting, and shading — all from your phone.',
        body: '<p>Premium outdoor spaces deserve premium technology. Livewire integrates weatherproof speakers, landscape and accent lighting, motorized shading, and outdoor displays — all controlled from a single app or voice command.</p>'
      };
    }

    // Kitchen / Bath
    if (type.indexOf('kitchen') !== -1 || type.indexOf('bath') !== -1) {
      return {
        headline: 'Renovating? Time to Upgrade Your Technology',
        subheadline: 'Lighting, audio, and smart features that match your investment.',
        body: '<p>A high-end kitchen or bath renovation is the ideal time to add under-cabinet lighting, in-ceiling speakers, mirror displays, and smart lighting control. Since walls and ceilings are already open, wiring is easy and costs are minimal.</p>'
      };
    }

    // Renovation / Addition / Remodel (general)
    if (tags.indexOf('remodel') !== -1 || tags.indexOf('addition') !== -1 || type.indexOf('renovation') !== -1) {
      return {
        headline: 'Your Renovation Deserves Smart Technology',
        subheadline: 'While the walls are open, make your home brilliant.',
        body: '<p>Major renovations are the most cost-effective time to add whole-home technology. Networking, lighting control, distributed audio, security cameras, and smart climate — all wired behind the walls before drywall goes up.</p><p>Livewire has been designing smart homes in Richmond for over 20 years. We handle everything from design to installation to lifetime support.</p>'
      };
    }

    // HVAC / Electrical (general trades)
    if (tags.indexOf('hvac') !== -1 || tags.indexOf('electrical') !== -1) {
      return {
        headline: 'Upgrading Your Home Systems?',
        subheadline: 'Add smart technology while the work is underway.',
        body: '<p>Electrical and HVAC upgrades are a natural opportunity to add smart thermostats, lighting automation, and whole-home networking. Livewire integrates with your existing contractors to make the process seamless.</p>'
      };
    }

    // Default
    return {
      headline: 'Your Home Deserves the Best Technology',
      subheadline: 'Smart home design, installation, and support — since 2003.',
      body: '<p>Livewire designs and installs premium home technology systems for Richmond-area homeowners. From networking and audio to lighting and security, we create technology experiences that are simple, reliable, and beautiful.</p>'
    };
  }
})();
