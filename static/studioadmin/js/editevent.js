;(function () {
  htmx.logAll();
  htmx.on("htmx:afterSwap", (e) => {
    // Response targeting #dialog => show the modal
    if (e.detail.target.id == "dialog") {
      $jq("#edit-event-modal").modal("show")
    }
  })

  htmx.on("htmx:beforeSwap", (e) => {
    console.log("htmx:beforeSwap", e)
    // Empty response targeting #dialog => hide the modal
    if (e.detail.target.id == "dialog" && !e.detail.xhr.response) {
      $jq("#edit-event-modal").modal("hide")
      e.detail.shouldSwap = false
    }
  })

  // Remove dialog content after hiding
  $jq("#edit-event-modal").on("hidden.bs.modal", () => {
    $jq("#dialog").empty()
  })
})()
