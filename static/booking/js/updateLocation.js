$jq(function () {

  var navtabs = document.getElementsByClassName('nav-tab');

  Array.from(navtabs).forEach(function (navtab) {
    navtab.addEventListener('click', function () {
      console.log(navtab.firstElementChild.text);
      document.getElementById('location').textContent = navtab.firstElementChild.text
    })
  });

});
