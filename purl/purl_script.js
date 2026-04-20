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
  var sig = params.get('sig');

  if (!pid || !sig) {
    // No permit ID or signature - show default content, don't fire webhook
    return;
  }

  // --- FIRE SCAN WEBHOOK ---
  fetch(WEBHOOK_URL + '?pid=' + encodeURIComponent(pid) + '&sig=' + encodeURIComponent(sig), {
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

    var segment = resolveSegment(data);
    var content = CONTENT_BY_SEGMENT[segment] || CONTENT_BY_SEGMENT['default'];

    headline.textContent = content.headline;
    if (subheadline) subheadline.textContent = content.subheadline;
    if (bodyText) bodyText.innerHTML = content.body;

    // Show the personalized section (hidden by default in Elementor)
    var personalSection = document.getElementById('purl-personalized');
    if (personalSection) {
      personalSection.style.display = 'block';
    }
  }

  // Mirrors pipeline/segmentation.py SEGMENT_PRIORITY + SEGMENT_TAG_MAP.
  // Keeping this in lock-step with the Python classifier prevents card/landing
  // page drift as new tags are added.
  var SEGMENT_PRIORITY = ['new_construction', 'major_remodel', 'kitchen_bath', 'outdoor_living'];
  var SEGMENT_TAG_MAP = {
    new_construction: ['new_construction', 'new construction', 'single family'],
    major_remodel:    ['addition', 'renovation', 'remodel', 'master suite', 'master bedroom'],
    kitchen_bath:     ['kitchen', 'bathroom'],
    outdoor_living:   ['pool', 'deck', 'patio', 'outdoor kitchen', 'detached garage']
  };

  // PURL landing pages stay more specific than postcard segments: Pool and
  // Deck/Outdoor share the outdoor_living postcard but get distinct landing
  // pages when the tag list tells us which one it is.
  function resolveSegment(data) {
    if (data.is_new_construction) return 'new_construction';

    var tagsRaw = data.permit_tags;
    var tagList = Array.isArray(tagsRaw)
      ? tagsRaw.map(function (t) { return String(t).toLowerCase(); })
      : String(tagsRaw || '').toLowerCase().split(/[,\s]+/).filter(Boolean);
    var tagSet = {};
    tagList.forEach(function (t) { tagSet[t] = true; });

    // Server-provided segment wins if present.
    if (data.segment && CONTENT_BY_SEGMENT[data.segment]) {
      // Refine outdoor_living into pool vs generic outdoor using tags.
      if (data.segment === 'outdoor_living' && tagSet['pool']) return 'pool';
      return data.segment;
    }

    // Pool gets its own page even though it rolls up under outdoor_living.
    if (tagSet['pool']) return 'pool';

    for (var i = 0; i < SEGMENT_PRIORITY.length; i++) {
      var seg = SEGMENT_PRIORITY[i];
      var keywords = SEGMENT_TAG_MAP[seg];
      for (var j = 0; j < keywords.length; j++) {
        if (tagSet[keywords[j]]) return seg;
      }
    }

    // Legacy fallback: pre-segmentation registries stored permit_tags as the
    // raw description string. Match against that blob before giving up.
    var blob = (typeof tagsRaw === 'string' ? tagsRaw : '').toLowerCase()
             + ' ' + String(data.permit_type || '').toLowerCase();
    if (blob.indexOf('pool') !== -1) return 'pool';
    for (var k = 0; k < SEGMENT_PRIORITY.length; k++) {
      var s = SEGMENT_PRIORITY[k];
      var kws = SEGMENT_TAG_MAP[s];
      for (var m = 0; m < kws.length; m++) {
        if (blob.indexOf(kws[m]) !== -1) return s;
      }
    }
    return 'default';
  }

  var CONTENT_BY_SEGMENT = {
    new_construction: {
      headline: 'Congratulations on Your New Home',
      subheadline: 'Make it smart from day one.',
      body: '<p>Building a new home is the perfect time to integrate technology seamlessly into every room. From whole-home networking and distributed audio to motorized shading and security, Livewire designs systems that work together beautifully — and last for decades.</p><p>We work directly with your builder to ensure everything is wired, programmed, and ready before you move in.</p>'
    },
    major_remodel: {
      headline: 'Your Renovation Deserves Smart Technology',
      subheadline: 'While the walls are open, make your home brilliant.',
      body: '<p>Major renovations are the most cost-effective time to add whole-home technology. Networking, lighting control, distributed audio, security cameras, and smart climate — all wired behind the walls before drywall goes up.</p><p>Livewire has been designing smart homes in Richmond for over 20 years. We handle everything from design to installation to lifetime support.</p>'
    },
    kitchen_bath: {
      headline: 'Renovating? Time to Upgrade Your Technology',
      subheadline: 'Lighting, audio, and smart features that match your investment.',
      body: '<p>A high-end kitchen or bath renovation is the ideal time to add under-cabinet lighting, in-ceiling speakers, mirror displays, and smart lighting control. Since walls and ceilings are already open, wiring is easy and costs are minimal.</p>'
    },
    pool: {
      headline: 'Your New Pool Deserves a Soundtrack',
      subheadline: 'Outdoor audio, lighting, and automation — designed for your space.',
      body: '<p>A luxury pool project is the perfect opportunity to add weatherproof speakers, landscape lighting control, pool automation, and outdoor surveillance. Livewire designs outdoor technology that looks invisible and sounds incredible.</p>'
    },
    outdoor_living: {
      headline: 'Bring Your Outdoor Living Space to Life',
      subheadline: 'Audio, lighting, and shading — all from your phone.',
      body: '<p>Premium outdoor spaces deserve premium technology. Livewire integrates weatherproof speakers, landscape and accent lighting, motorized shading, and outdoor displays — all controlled from a single app or voice command.</p>'
    },
    'default': {
      headline: 'Your Home Deserves the Best Technology',
      subheadline: 'Smart home design, installation, and support — since 2003.',
      body: '<p>Livewire designs and installs premium home technology systems for Richmond-area homeowners. From networking and audio to lighting and security, we create technology experiences that are simple, reliable, and beautiful.</p>'
    }
  };
})();
