jQuery(document).ready(function () {

  var navtabs = document.getElementsByClassName('nav-tab');

  Array.from(navtabs).forEach(function (navtab) {
    navtab.addEventListener('click', function () {
      console.log(navtab.firstChild.text);
      document.getElementById('location').textContent = navtab.firstChild.text
    })
  });

});