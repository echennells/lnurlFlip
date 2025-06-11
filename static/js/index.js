/* globals Quasar, Vue, _, VueQrcode, windowMixin, LNbits, LOCALE */

const mapLnurlFlip = obj => {
  obj._data = _.clone(obj)
  obj.date = LNbits.utils.formatDateString(obj.created_at) || new Date().toLocaleString()
  obj.comment_count = obj.comment_count || 0
  return obj
}

window.app = Vue.createApp({
  el: '#vue',
  mixins: [window.windowMixin],
  data() {
    return {
      flips: [],
      flipsTable: {
        columns: [
          {
            name: 'name',
            label: 'Name',
            align: 'left',
            field: 'name',
            sortable: true
          },
          {
            name: 'wallet',
            label: 'Wallet',
            align: 'left',
            field: 'wallet',
            format: (val) => {
              const wallet = this.g.user.wallets.find(w => w.id === val)
              return wallet ? wallet.name : 'Unknown'
            }
          },
          {
            name: 'balance',
            label: 'Balance',
            align: 'right',
            field: 'balance',
            format: val => `${Math.floor((val || 0) / 1000)} sats`
          },
          {
            name: 'uses',
            label: 'Uses',
            align: 'right',
            field: 'uses',
            sortable: true
          }
        ],
        pagination: {
          rowsPerPage: 10
        }
      },
      lnurlpOptions: [],
      lnurlwOptions: [],
      formDialog: {
        show: false,
        data: {}
      },
      qrCodeDialog: {
        show: false,
        data: null,
        qrValue: ''
      },
      commentsDialog: {
        show: false,
        loading: false,
        comments: []
      }
    }
  },
  methods: {
    async getFlips() {
      try {
        const response = await LNbits.api.request(
          'GET',
          '/lnurlFlip/api/v1/myex?all_wallets=true',
          this.g.user.wallets[0].inkey
        )
        
        // Fetch balance for each flip
        const flipsWithBalance = await Promise.all(
          response.data.map(async (flip) => {
            try {
              const balanceResponse = await LNbits.api.request(
                'GET',
                `/lnurlFlip/api/v1/balance/${flip.id}`,
                this.g.user.wallets[0].inkey
              )
              return {
                ...mapLnurlFlip(flip),
                balance: balanceResponse.data.balance || 0
              }
            } catch (error) {
              console.error(`Error fetching balance for ${flip.id}:`, error)
              return {
                ...mapLnurlFlip(flip),
                balance: 0
              }
            }
          })
        )
        
        this.flips = flipsWithBalance
      } catch (error) {
        console.error('Error fetching flips:', error)
        LNbits.utils.notifyApiError(error)
      }
    },

    async getLnurlPayLinks() {
      try {
        const response = await LNbits.api.request(
          'GET',
          '/lnurlp/api/v1/links',
          this.g.user.wallets[0].inkey
        )
        
        if (Array.isArray(response.data)) {
          this.lnurlpOptions = response.data.map(link => ({
            label: `${link.description} (${link.min === link.max ? link.min : `${link.min} - ${link.max}`} sats)`,
            value: link.id,
            lnurl: link.lnurl
          }))
        }
      } catch (error) {
        console.error('Error fetching LNURL pay links:', error)
        LNbits.utils.notifyApiError(error)
      }
    },

    async getLnurlWithdrawLinks() {
      try {
        const response = await LNbits.api.request(
          'GET',
          '/withdraw/api/v1/links?all_wallets=true&limit=10&offset=0',
          this.g.user.wallets[0].adminkey
        )
        
        if (response.data && response.data.data) {
          const filteredLinks = this.formDialog.data.wallet 
            ? response.data.data.filter(link => link.wallet === this.formDialog.data.wallet)
            : response.data.data

          this.lnurlwOptions = filteredLinks.map(link => {
            const minSats = link.min_withdrawable || 0
            const maxSats = link.max_withdrawable || 0
            const amountDisplay = minSats === maxSats 
              ? `${minSats} sats` 
              : `${minSats} - ${maxSats} sats`
            
            return {
              label: `${link.title || 'Untitled'} (${amountDisplay})`,
              value: link.id,
              lnurl: link.lnurl,
              min: link.min_withdrawable || 0,
              max: link.max_withdrawable || 0
            }
          })
        }
      } catch (error) {
        console.error('Error fetching LNURL withdraw links:', error)
        LNbits.utils.notifyApiError(error)
      }
    },

    openFormDialog() {
      this.formDialog.data = {
        name: '',
        wallet: this.g.user.wallets[0]?.id || null,
        selectedLnurlp: null,
        selectedLnurlw: null
      }
      this.formDialog.show = true
    },

    closeFormDialog() {
      this.formDialog.show = false
      this.formDialog.data = {}
    },

    saveFlip() {
      const wallet = _.findWhere(this.g.user.wallets, {
        id: this.formDialog.data.wallet
      })
      const data = _.clone(this.formDialog.data)
      
      if (data.id) {
        this.updateFlip(wallet, data)
      } else {
        this.createFlip(wallet, data)
      }
    },

    updateFlip(wallet, data) {
      LNbits.api
        .request(
          'PUT',
          '/lnurlFlip/api/v1/myex/' + data.id,
          wallet.adminkey,
          data
        )
        .then(response => {
          this.flips = _.reject(this.flips, obj => obj.id === data.id)
          this.flips.push(mapLnurlFlip(response.data))
          this.formDialog.show = false
          this.resetFormData()
        })
        .catch(err => {
          LNbits.utils.notifyApiError(err)
        })
    },

    createFlip(wallet, data) {
      LNbits.api
        .request('POST', '/lnurlFlip/api/v1/myex', wallet.adminkey, data)
        .then(response => {
          this.getFlips()
          this.formDialog.show = false
          this.resetFormData()
        })
        .catch(err => {
          LNbits.utils.notifyApiError(err)
        })
    },

    resetFormData() {
      this.formDialog = {
        show: false,
        data: {}
      }
    },

    editFlip(flipId) {
      const universal = this.flips.find(u => u.id === flipId)
      if (!universal) return
      
      this.formDialog.data = { ...universal._data }
      this.formDialog.show = true
    },

    async deleteUniversal(flipId) {
      const flip = this.flips.find(u => u.id === flipId)
      if (!flip) return

      LNbits.utils
        .confirmDialog('Are you sure you want to delete this LNURL Flip?')
        .onOk(async () => {
          try {
            await LNbits.api.request(
              'DELETE',
              `/lnurlFlip/api/v1/myex/${flipId}`,
              this.g.user.wallets[0].adminkey
            )
            
            await this.getFlips()
            
            this.$q.notify({
              type: 'positive',
              message: 'LNURL Flip deleted successfully',
              timeout: 5000
            })
          } catch (error) {
            console.error('Error deleting flip:', error)
            LNbits.utils.notifyApiError(error)
          }
        })
    },

    async openQrCodeDialog(flipId) {
      const flip = this.flips.find(u => u.id === flipId)
      if (!flip) return

      try {
        const response = await LNbits.api.request(
          'GET',
          `/lnurlFlip/api/v1/lnurl/${flipId}`,
          this.g.user.wallets[0].inkey
        )
        
        this.qrCodeDialog.data = flip
        this.qrCodeDialog.qrValue = response.data
        this.qrCodeDialog.show = true
      } catch (error) {
        console.error('Error fetching LNURL:', error)
        LNbits.utils.notifyApiError(error)
      }
    },

    async showComments(flipId) {
      this.commentsDialog.show = true
      this.commentsDialog.loading = true
      this.commentsDialog.comments = []

      try {
        const response = await LNbits.api.request(
          'GET',
          `/lnurlFlip/api/v1/comments/${flipId}`,
          this.g.user.wallets[0].inkey
        )
        
        this.commentsDialog.comments = response.data || []
      } catch (error) {
        console.error('Error loading comments:', error)
        LNbits.utils.notifyApiError(error)
      } finally {
        this.commentsDialog.loading = false
      }
    },

    formatDate(timestamp) {
      return new Date(timestamp * 1000).toLocaleString()
    },

    formatSats(msats) {
      return Math.floor((msats || 0) / 1000)
    },

    exportCSV() {
      LNbits.utils.exportCSV(
        this.flipsTable.columns,
        this.flips,
        'lnurlflips'
      )
    },

    copyText(text, message = 'LNURL copied to clipboard!') {
      Quasar.copyToClipboard(text).then(() => {
        this.$q.notify({
          message: message,
          color: 'positive',
          position: 'bottom',
          timeout: 2000
        })
      })
    },

    connectWebSocket(walletId) {
      if (!walletId) return
      
      const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
      const url = `${protocol}//${location.host}/api/v1/ws/${walletId}`
      
      this.connection = new WebSocket(url)
      
      this.connection.onmessage = async (e) => {
        try {
          const data = JSON.parse(e.data)
          if (data.flip_id) {
            // Update balance for specific flip
            const flip = this.flips.find(u => u.id === data.flip_id)
            if (flip) {
              flip.balance = data.balance || 0
            }
          }
        } catch (error) {
          console.error('WebSocket message error:', error)
        }
      }
    }
  },
  watch: {
    'formDialog.show': function(newVal) {
      if (newVal) {
        // Initialize form data when dialog opens
        if (!this.formDialog.data.id) {
          this.formDialog.data = {
            name: '',
            wallet: this.g.user.wallets[0]?.id || null,
            lnurlwithdrawamount: null,
            selectedLnurlp: null,
            selectedLnurlw: null
          }
        }
        this.getLnurlPayLinks()
        this.getLnurlWithdrawLinks()
      }
    },
    'formDialog.data.wallet': function(newVal) {
      if (newVal) {
        this.getLnurlPayLinks()
        this.getLnurlWithdrawLinks()
      }
    }
  },
  created() {
    if (this.g.user.wallets && this.g.user.wallets.length > 0) {
      this.getFlips()
      this.connectWebSocket(this.g.user.wallets[0].id)
    }
  }
})
