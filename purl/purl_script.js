/**
 * PERMIT MINER: PURL Landing Page Script
 *
 * Drop this into the WordPress/Elementor page at getlivewire.com/welcome
 * Reads the permit type from the URL to swap content immediately,
 * then fires the scan webhook in the background.
 *
 * Usage: Add as a Custom HTML widget in Elementor, or enqueue via
 * functions.php / Code Snippets plugin.
 */

(function () {
  'use strict';

  var WEBHOOK_URL = 'https://www.getlivewire.com/permit-scan';

  var params = new URLSearchParams(window.location.search);
  var pid = params.get('pid');
  var sig = params.get('sig');
  var ptype = params.get('ptype');

  // Swap content immediately from URL param (no server round-trip needed)
  if (ptype) {
    updatePageContent(ptype);
  }

  if (!pid || !sig) {
    return;
  }

  // Fire scan webhook in background
  fetch(WEBHOOK_URL + '?pid=' + encodeURIComponent(pid) + '&sig=' + encodeURIComponent(sig), {
    method: 'GET',
    mode: 'cors'
  }).catch(function (err) {
    console.log('Permit Miner: webhook error', err);
  });

  function updatePageContent(type) {
    var headline = document.getElementById('purl-headline');
    var subheadline = document.getElementById('purl-subheadline');
    var bodyText = document.getElementById('purl-body');

    if (!headline) return;

    var content = getContentByType(type);

    headline.textContent = content.headline;
    if (subheadline) subheadline.textContent = content.subheadline;
    if (bodyText) bodyText.innerHTML = content.body;

    var personalSection = document.getElementById('purl-personalized');
    if (personalSection) {
      personalSection.style.display = 'block';
    }
  }

  function getContentByType(type) {
    var variants = {
      'new_construction': {
        headline: 'Congratulations on Your New Home',
        subheadline: 'Make it smart from day one.',
        body: '<p>Building a new home is the perfect time to integrate technology seamlessly into every room. From whole-home networking and distributed audio to motorized shading and security, Livewire designs systems that work together beautifully — and last for decades.</p><p>We work directly with your builder to ensure everything is wired, programmed, and ready before you move in.</p>'
      },
      'outdoor': {
        headline: 'Your New Pool Deserves a Soundtrack',
        subheadline: 'Outdoor audio, lighting, and automation — designed for your space.',
        body: '<p>A luxury pool or outdoor living project is the perfect opportunity to add weatherproof speakers, landscape lighting control, pool automation, and outdoor surveillance. Livewire designs outdoor technology that looks invisible and sounds incredible.</p>'
      },
      'kitchen_bath': {
        headline: 'Renovating? Time to Upgrade Your Technology',
        subheadline: 'Lighting, audio, and smart features that match your investment.',
        body: '<p>A high-end kitchen or bath renovation is the ideal time to add under-cabinet lighting, in-ceiling speakers, mirror displays, and smart lighting control. Since walls and ceilings are already open, wiring is easy and costs are minimal.</p>'
      },
      'remodel': {
        headline: 'Your Renovation Deserves Smart Technology',
        subheadline: 'While the walls are open, make your home brilliant.',
        body: '<p>Major renovations are the most cost-effective time to add whole-home technology. Networking, lighting control, distributed audio, security cameras, and smart climate — all wired behind the walls before drywall goes up.</p><p>Livewire has been designing smart homes in Richmond for over 20 years. We handle everything from design to installation to lifetime support.</p>'
      }
    };

    return variants[type] || {
      headline: 'Your Home Deserves the Best Technology',
      subheadline: 'Smart home design, installation, and support — since 2003.',
      body: '<p>Livewire designs and installs premium home technology systems for Richmond-area homeowners. From networking and audio to lighting and security, we create technology experiences that are simple, reliable, and beautiful.</p>'
    };
  }
})();
