# -*- encoding: utf-8 -*-
#################################################################################
#                                                                               #
# Copyright (C) 2013 Agtis Consultoria                                          #
#                                                                               #
#This program is free software: you can redistribute it and/or modify           #
#it under the terms of the GNU Affero General Public License as published by    #
#the Free Software Foundation, either version 3 of the License, or              #
#(at your option) any later version.                                            #
#                                                                               #
#This program is distributed in the hope that it will be useful,                #
#but WITHOUT ANY WARRANTY; without even the implied warranty of                 #
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the                  #
#GNU Affero General Public License for more details.                            #
#                                                                               #
#You should have received a copy of the GNU Affero General Public License       #
#along with this program.  If not, see <http://www.gnu.org/licenses/>.          #
#################################################################################


from osv import fields, osv
import httplib, urllib ,base64,requests
import netsvc
from pprint import  pprint
from requests.exceptions import ConnectionError
import libxml2
from tools import config
from tools.translate import _
import decimal_precision as dp
import random
import sys, os
from datetime import datetime

import re, string
from unicodedata import normalize

import time





LOGGER = netsvc.Logger()




class invoice(osv.osv):
    _inherit = "account.invoice"
    _columns = {
        'state': fields.selection([
            ('draft','Draft'),
            ('proforma','Pro-forma'),
            ('proforma2','Pro-forma'),
            ('open','Open'),
            ('sefaz_export','Enviar para Receita'),
            ('sefaz_out','Recebida pela SEFAZ'),
            ('sefaz_exception','Erro de autorização da Receita'),
            ('paid','Paid'),
            ('cancel','Cancelled'),
            ('sefaz_denied','Uso Denegado'),
            ('sefaz_cancel','Cancelado na SEFAZ')
            ],'State', select=True, readonly=True,
            help=' * The \'Draft\' state is used when a user is encoding a new and unconfirmed Invoice. \
            \n* The \'Pro-forma\' when invoice is in Pro-forma state,invoice does not have an invoice number. \
            \n* The \'Open\' state is used when user create invoice,a invoice number is generated.Its in open state till user does not pay invoice. \
            \n* The \'Paid\' state is set automatically when invoice is paid.\
            \n* The \'sefaz_out\' Gerado aquivo de exportação para sistema daReceita.\
            \n* The \'Cancelled\' state is used when user cancel invoice.'),
        'nfe_status': fields.char('Status na Sefaz', size=500, readonly=True),
    }
    


    def finalize_invoice_move_lines(self, cr, uid, invoice_browse, move_lines):

        move_lines = super(invoice, self).finalize_invoice_move_lines(cr, uid, invoice_browse, move_lines)

        icms_value = 0.0
        icms_base = 0.0
        icms_percent=0.0
        
        for line in invoice_browse.invoice_line:
            icms_base += line.icms_base
            icms_value += line.icms_value    

        if icms_base > 0:
            icms_percent = round((icms_value/icms_base)*100,2)
            if "*valoricms*" in invoice_browse.comment:
                comment = invoice_browse.comment.replace("*valoricms*","%s" %(icms_value)).replace("*aliquotaicms*","%s" %(icms_percent))
                invoice_browse.write({'comment': comment})

            
        return move_lines

    def onchange_fiscal_operation_id(self, cr, uid, ids, partner_address_id=False, partner_id=False, company_id=False, fiscal_operation_category_id=False, fiscal_operation_id=False):

        print"h============================================ onchange_fiscal_operation_id fiscal_operation_id na entrada = ", fiscal_operation_id

        result = {'value': {} }
        if not company_id or not fiscal_operation_category_id:
            return result
        fiscal_data = self._fiscal_position_map(cr, uid, ids, partner_id, partner_address_id, company_id, fiscal_operation_category_id, fiscal_operation_id=fiscal_operation_id)
        result['value'].update(fiscal_data)
        print "=============================h1"
        if fiscal_operation_id:
            print "=============================h2"
            obj_foperation = self.pool.get('l10n_br_account.fiscal.operation').browse(cr, uid, fiscal_operation_id)
            for inv in self.browse(cr, uid, ids):
                print "=============================h3"
                for line in inv.invoice_line:
                    print "=============================agtis h4"
                    line.write({'cfop_id': obj_foperation.cfop_id.id,
                                'fiscal_operation_id': obj_foperation.id,
                                'fiscal_position_id': result['value']['fiscal_position']
                     })
        print"i============================================ onchange_fiscal_operation_id ",pprint(result)

        return result





    def _fiscal_position_map(self, cr, uid, ids, partner_id, partner_invoice_id, company_id, fiscal_operation_category_id, fiscal_operation_id=False):

        print"a============================================ _fiscal_position_map do item l10n_br entrada "
        result = {'fiscal_operation_id': False, 
                  'fiscal_document_id': False, 
                  'document_serie_id': False,
                  'journal_id': False,}
        obj_rule = self.pool.get('account.fiscal.position.rule')
        obj_fo_category = self.pool.get('l10n_br_account.fiscal.operation.category')

        if not fiscal_operation_category_id:
            pass
        else:
            print"c============================================ vai entrar em fiscal_rule ",pprint(result)

            fiscal_result = obj_rule.fiscal_position_map(cr, uid, partner_id, partner_invoice_id, company_id, fiscal_operation_category_id, context={'use_domain': ('use_invoice', '=', True)}
                ,fiscal_operation_id=fiscal_operation_id)   
            print" fiscal_result =  ",pprint(fiscal_result)
            result.update(fiscal_result)
            
            if result.get('fiscal_operation_id', False):
                obj_foperation = self.pool.get('l10n_br_account.fiscal.operation').browse(cr, uid, result['fiscal_operation_id'])
                result['fiscal_document_id'] = obj_foperation.fiscal_document_id.id

                obj_company = self.pool.get('res.company').browse(cr, uid, company_id)
                document_serie_id = [doc_serie for doc_serie in obj_company.document_serie_product_ids if doc_serie.fiscal_document_id.id == obj_foperation.fiscal_document_id.id and doc_serie.active]
                if not document_serie_id:
                    raise osv.except_osv(_('Nenhuma série de documento fiscal !'),_("Empresa não tem uma série de documento fiscal cadastrada: '%s', você deve informar uma série no cadastro de empresas") % (obj_company.name,))
                else:
                    result['document_serie_id'] = document_serie_id[0].id
                for inv in self.browse(cr, uid, ids):
                    for line in inv.invoice_line:
                        line.cfop_id = obj_foperation.cfop_id.id
                
                if fiscal_operation_category_id:
                    fo_category = obj_fo_category.browse(cr, uid, fiscal_operation_category_id)
                    journal_ids = [journal for journal in fo_category.journal_ids if journal.company_id.id == company_id]
                    if not journal_ids:
                        raise osv.except_osv(_('Nenhuma Diário !'),_("Categoria de operação fisca: '%s', não tem um diário contábil para a empresa %s") % (fo_category.name, obj_company.name))
                    else:
                        result['journal_id'] = journal_ids[0].id
            print"d============================================ _fiscal_position_map do item l10n_br saida 2",pprint(result)


        fo_obj = self.pool.get('l10n_br_account.fiscal.operation')
        if result.has_key('fiscal_operation_id') and result['fiscal_operation_id']:
            fo = fo_obj.browse(cr, uid, result['fiscal_operation_id'])
            if fo.inv_copy_note:
                result['comment'] = fo.note
        print"j============================================ _fiscal_position_map da agtis ",pprint(result)
        return result
    
    def nfe_edoc_send(self, cr, uid, ids, context=None):

        fatura_obj = self.pool.get("account.invoice")
        faturas = fatura_obj.browse(cr, uid, ids)

        for fatura in faturas:
            print ("Enviando a fatura: %s.") % (fatura.id,)

            batch= fatura.return_max_batch_for_invoice(fatura=fatura)
            reenvio_de_nota=False
            
            if batch:
                              
                retorno = batch.return_edoc.split('|')
                if retorno[0]=='REJEITADA':
                    reenvio_de_nota=True
                elif retorno[0]=='EXCEPTION':
                    consulta = fatura.nfe_edoc_consult_lote(filtro="nlote="+str(batch.batch_number),campos="situacao,chave")
                    if consulta[0] == 'REGISTRADA':
                        fatura.nfe_edoc_trash(chave=consulta[1])
                    
                    reenvio_de_nota=True
                    
                elif retorno[0]=='DENEGADA':
                    self.log(cr, uid, 0, retorno[1])
                elif retorno[0]=='ENVIADA' or retorno[0]=='OUTRO':
                    fatura.nfe_edoc_resolve(batch=batch)
                
                

            if not batch or reenvio_de_nota :
                batch_obj = self.pool.get('account.invoice.nfe.batch')
                batch = batch_obj.browse(cr,uid,batch_obj.create_record_batch(cr, uid, ids, context=context,invoice_id=fatura.id))
                strNota = "NumLote= %s\nFormato=REC\n" %(batch.batch_number)
                strNota += fatura.nfe_export_txt(fatura.company_id.edoc_nfe_environment) 
                dados = fatura.get_edoc_data()
                dados.update({"arquivo":strNota})
                
                host = "http://%s:%s/ManagerAPIWeb/nfe/envia" %(dados["ip"],dados["porta"])
                              
                params = urllib.urlencode(dados)
                
                #------------------------------verificação de erros---------------------- 
                try:
                    response = requests.post(host,params=params,auth=(dados["usuario"],dados["senha"]))
                except ConnectionError,erro:
                    #descobrir como obter o codigo de erro da Exception
                    raise osv.except_osv('Erro','Não foi possivel conectar ao software gerenciador de NF-e -> erro: ')
                
                
                status_code = str(response.status_code)
                if status_code != '200':
                    raise osv.except_osv("Erro","Erro de requisicao codigo: %s") %(status_code)
                
                
                list_response = response.text.split("|")
                
                self.log(cr, uid, 1, "Envio de Nota: Retorno=%s" % response.text)
                retorno = fatura.nfe_edoc_translate_response(batch=batch,fatura=fatura,list_response=list_response)
                if  retorno=='OK':
                    fatura.nfe_send_mail()
                
                
                return True
            
            
    def nfe_edoc_attachments(self, cr, uid, ids, context=None):
        fatura_obj = self.pool.get("account.invoice")
        attach_obj = self.pool.get("ir.attachment")
        
        faturas = fatura_obj.browse(cr, uid, ids)
        for fatura in faturas:
            attachment_ids = attach_obj.search(cr, uid, [ ('res_model','=','account.invoice'),
                                                      ('res_id','=', fatura.id ),
                                                    ] )
            has_pdf = False
            has_xml = False        
            for att in attach_obj.browse(cr, uid, attachment_ids):
                if att.name == ('%s-danfe.pdf' % fatura.nfe_access_key): has_pdf = True
                if att.name == ('%s-nfe.xml' % fatura.nfe_access_key): has_xml = True
            
            dados = fatura.get_edoc_data()
            dados.update({"chavenota":fatura.nfe_access_key,"url":"0"})
            params = urllib.urlencode(dados)
            
            if not has_pdf:
                print ("Anexando PDF da fatura: %s.") % (fatura.id,)
    
                host = "http://%s:%s/ManagerAPIWeb/nfe/imprime" %(dados["ip"],dados["porta"])
                response = requests.get(host,params=params,
                    auth=(dados["usuario"],dados["senha"]))
    
                self.pool.get('ir.attachment').create(cr,uid,
                   {
                     'name':'%s-danfe.pdf' % fatura.nfe_access_key,
                     'datas': base64.encodestring(response.content),
                     'datas_fname':'%s-danfe.pdf' % fatura.nfe_access_key,
                     'type' : 'binary',
                     'res_model':'account.invoice',
                     'res_id':fatura.id
                   })

            if not has_xml:
                print ("Anexando XML da NF-e na fatura: %s.") % (fatura.id,)
    
                host = "http://%s:%s/ManagerAPIWeb/nfe/xml" %(dados["ip"],dados["porta"])
                response = requests.get(host,params=params,
                    auth=(dados["usuario"],dados["senha"]))
    
                self.pool.get('ir.attachment').create(cr,uid,
                   {
                     'name':'%s-nfe.xml' % fatura.nfe_access_key,
                     'datas': base64.encodestring(response.content),
                     'datas_fname':'%s-nfe.xml' % fatura.nfe_access_key,
                     'type' : 'binary',
                     'res_model':'account.invoice',
                     'res_id':fatura.id
                   })

        return True

    def nfe_edoc_resolve(self, cr, uid, ids, context=None,batch=None):
        
        fatura_obj = self.pool.get("account.invoice")
        faturas = fatura_obj.browse(cr, uid, ids)
        for fatura in faturas:
            print ("Resolvendo fatura: %s.") % (fatura.id,)
            dados = fatura.get_edoc_data()
            dados.update({"chavenota":fatura.nfe_access_key})
            
            params = urllib.urlencode(dados)
            host = "http://%s:%s/ManagerAPIWeb/nfe/resolve" %(dados["ip"],dados["porta"])
            response = requests.get(host,params=params,auth=(dados["usuario"],dados["senha"]))
            list_response = response.text.split('|')
            
            self.log(cr, uid, 5, "Resolver nota: Retorno=%s" % response.text)
            fatura.nfe_edoc_translate_response(batch=batch,fatura=fatura,list_response=list_response)
           
        return True
    
    def nfe_edoc_translate_response(self, cr, uid, ids, context=None,batch=None,fatura=None,list_response=None):
        wf_service = netsvc.LocalService("workflow")
        if list_response[0] == "EXCEPTION":
            fatura.write({'nfe_status':'Erro: '+ list_response[2]})
            batch.write({'return_edoc': "EXCEPTION|"+list_response[2]})
            wf_service.trg_validate(uid, 'account.invoice', fatura.id, 'sefaz_exception', cr)
            cr.commit()
            
            # TRAZER O CODIGO DE VERIFICAÇÃO DE EXCEPTION PARA CÁ
            
        elif list_response[2] in[ "110","301","302"]:
            fatura.write({'nfe_access_key':list_response[1],'nfe_status':list_response[2]+" - "+list_response[3]})
            batch.write({'return_edoc': "DENEGADA|"+list_response[3]})
            wf_service.trg_validate(uid, 'account.invoice', fatura.id, 'sefaz_denied', cr)
            cr.commit()
            
        elif list_response[2] in ["103","105"]:
            fatura.write({'nfe_access_key':list_response[1],'nfe_status':list_response[2]+" - "+list_response[3]})
            batch.write({'return_edoc': "ENVIADA|"+list_response[3]})
            wf_service.trg_validate(uid, 'account.invoice', fatura.id, 'sefaz_received_xml', cr)
            cr.commit()
            
        elif list_response[2] == "100":
            fatura.write({'nfe_access_key':list_response[1],'nfe_status':list_response[2]+" - "+list_response[3]})
            batch.write({'return_edoc': "AUTORIZADA|"+list_response[3]})
            wf_service.trg_validate(uid, 'account.invoice', fatura.id, 'sefaz_authorized', cr)
            cr.commit()
            return "OK"
            
            
        elif int(list_response[2]) >= 201:
            fatura.write({'nfe_access_key':list_response[1],'nfe_status':list_response[2]+" - "+list_response[3]})
            batch.write({'return_edoc': "REJEITADA|"+list_response[3]})
            wf_service.trg_validate(uid, 'account.invoice', fatura.id, 'sefaz_exception', cr)
            cr.commit()
        
        else:
            fatura.write({'nfe_access_key':list_response[1],'nfe_status':list_response[2]+" - "+list_response[3]})
            batch.write({'return_edoc': "OUTRO|"+list_response[3]})
            wf_service.trg_validate(uid, 'account.invoice', fatura.id, 'sefaz_exception', cr)
            cr.commit()
        return True
      
    def nfe_edoc_trash(self, cr, uid, ids, context=None,chave=None):
        fatura_obj = self.pool.get("account.invoice")
        faturas = fatura_obj.browse(cr, uid, ids)
        for fatura in faturas:
            print ("Executando descarte na fatura: %s.") % (fatura.id,)
            dados = fatura.get_edoc_data()
            dados.update({"chavenota":chave})
        
            host = "http://%s:%s/ManagerAPIWeb/nfe/descarta" %(dados["ip"],dados["porta"])
            params = urllib.urlencode(dados)
            
            response = requests.post(host,params=params,auth=(dados["usuario"],dados["senha"]))
            
            list_response = response.text.split("|")     
            self.log(cr, uid, 3, "Descarte de Lote: Retorno=%s" % response.text)
            if list_response[0] == "EXCEPTION":
                self.log(cr, uid, 4, "Descarte de Lote: Retorno=%s" % response.text)

        return True

    def nfe_edoc_consult(self, cr, uid, ids, context=None):

        fatura_obj = self.pool.get("account.invoice")
        faturas = fatura_obj.browse(cr, uid, ids)
        for fatura in faturas:
            print ("Executando consulta na fatura: %s.") % (fatura.id,)
            dados = fatura.get_edoc_data()
            filtro = "chave=" + fatura.nfe_access_key
            
            dados.update({"filtro":filtro,"campos":"nrecibo,chave,situacao,nlote"})
            
            params = urllib.urlencode(dados)
            host = "http://%s:%s/ManagerAPIWeb/nfe/consulta" %(dados["ip"],dados["porta"])
            response = requests.get(host,params=params,auth=(dados["usuario"],dados["senha"]))

            
            self.log(cr, uid, 5, "Consulta de nota: Retorno=%s" % response.text)
            list_response = response.text.split('|')
            if list_response[0]=="EXCEPTION":
                self.log(cr, uid, 9, response.text)
            elif list_response[2]== 'ENVIADA' or list_response[2]== 'RECEBIDA' or list_response[2]== 'REGISTRADA':
                batch_obj = self.pool.get('account.invoice.nfe.batch')
                batch_id = batch_obj.search(cr,uid,args=[('batch_number','=',list_response[3]),('invoice_id','=',str(fatura.id))],limit=1)
                if isinstance(batch_id, list):
                    batch_id = batch_id[0]
                batch = batch_obj.browse(cr,uid,batch_id)
                fatura.nfe_edoc_resolve(batch=batch)
                #nova consulta
                response = requests.get(host,params=params,auth=(dados["usuario"],dados["senha"]))
                list_response = response.text.split('|')
                return list_response
        return list_response
    
    def nfe_edoc_consult_lote(self, cr, uid, ids, context=None,filtro=None,campos=None):
    
        fatura_obj = self.pool.get("account.invoice")
        faturas = fatura_obj.browse(cr, uid, ids)
        for fatura in faturas:
            print ("Executando consulta na fatura: %s.") % (fatura.id,)
            dados = fatura.get_edoc_data()    
            dados.update({"filtro":filtro,"campos":campos})
            
            params = urllib.urlencode(dados)
            host = "http://%s:%s/ManagerAPIWeb/nfe/consulta" %(dados["ip"],dados["porta"])
            response = requests.get(host,params=params,auth=(dados["usuario"],dados["senha"]))
            list_situacao = response.text.split("|")
            
            self.log(cr, uid, 5, "Consulta de nota: Retorno=%s" % response.text)
        return list_situacao
    
    def nfe_edoc_cancel(self, cr, uid, ids, context=None,justificativa=''):
        
        wf_service = netsvc.LocalService("workflow")
        fatura_obj = self.pool.get("account.invoice")
        faturas = fatura_obj.browse(cr, uid, ids)
        for fatura in faturas:
            print ("Executando cancelamento na fatura: %s.") % (fatura.id,)
            dados = fatura.get_edoc_data()
            dados.update({"justificativa":justificativa,"chavenota":fatura.nfe_access_key})
            
            params = urllib.urlencode(dados)
            
        
            host = "http://%s:%s/ManagerAPIWeb/nfe/cancela" %(dados["ip"],dados["porta"])
            params = urllib.urlencode(dados)
            
            response = requests.post(host,params=params,auth=(dados["usuario"],dados["senha"]))
            self.log(cr, uid, 8, "Cancelamento: Retorno=%s" % response.text)
            
            list_response = response.text.split('|')
            if list_response[1] == "135":
                fatura.write({'nfe_status': 'Cancelada'})
                wf_service.trg_validate(uid, 'account.invoice', fatura.id, 'sefaz_cancel_authorized', cr)
            else:
                if list_response[0] != "EXCEPTION":
                    #nrecibo,chave,situacao,nlote
                    consulta = fatura.nfe_edoc_consult()
                    if consulta[2]=="CANCELADA":
                        fatura.write({'nfe_status': 'Cancelada'})
                        wf_service.trg_validate(uid, 'account.invoice', fatura.id, 'sefaz_cancel_authorized', cr)
                        self.log(cr, uid, 9, "Confirmacao do Cancelamento: Retorno=%s" % consulta[2])
                    
                
                
                             
        return True   

    def nfe_send_mail(self, cr, uid, ids, context=None):
        if not context:
            context={}
        fatura_obj = self.pool.get("account.invoice")
        attach_obj = self.pool.get('ir.attachment')
        msg_pool = self.pool.get('mail.message')
        mail_server_obj = self.pool.get('ir.mail_server')
        mail_server_id = mail_server_obj.search(cr, uid,
                args=[('name', 'like', '%#envionfe%')])

        if mail_server_id:
            if isinstance(mail_server_id, list):
                mail_server_id = mail_server_id[0]
            mail_server_brw = mail_server_obj.browse(cr, uid, mail_server_id)
            try:
                email_from = mail_server_brw.smtp_user
            except:
                pass

        faturas = fatura_obj.browse(cr, uid, ids)
        for fatura in faturas:
            fatura.nfe_edoc_attachments()
            if fatura.partner_id.email:
                attachment_ids = attach_obj.search(cr, uid, [ ('res_model','=','account.invoice'),
                                                          ('res_id','=', fatura.id ),
                                                        ] )
                data_pdf = False
                data_xml = False        
                for att in attach_obj.browse(cr, uid, attachment_ids):
                    if att.name == ('%s-danfe.pdf' % fatura.nfe_access_key): data_pdf = base64.decodestring(att.datas) 
                    if att.name == ('%s-nfe.xml' % fatura.nfe_access_key): data_xml = base64.decodestring(att.datas)
                    
                
                #TODO: enviar o mail_server_id cfme campo novo a ser criado na empresa na aba edoc
                msg_id = msg_pool.schedule_with_attach(cr, uid, 
		   email_from=email_from,
                    email_to=[  '%s' % fatura.partner_id.email ],
                    
                    subject=fatura.company_id.edoc_nfe_email_subject,
                    body=fatura.company_id.edoc_nfe_email_text_send,
                    attachments={'%s-danfe.pdf' % fatura.nfe_access_key: data_pdf,
                                 '%s-nfe.xml' % fatura.nfe_access_key: data_xml
                                 }, 
                    context=context)
                
                self.pool.get('mail.message').browse(cr, uid, msg_id).send()
                self.log(cr, uid, 7, "Email enviado com sucesso")
            else:
                self.log(cr, uid, 8, "O email nao foi criado por que não há email de parceiro cadastrado")
                
    
    def nfe_edoc_email(self, cr, uid, ids, context=None):
        fatura_obj = self.pool.get("account.invoice")
        faturas = fatura_obj.browse(cr, uid, ids)
        for fatura in faturas:
            print ("Executando envio de email da fatura: %s.") % (fatura.id,)
            dados = fatura.get_edoc_data()
            dados.update({"chavenota":fatura.nfe_access_key,
                          "emaildestinatario": fatura.partner_id.email,
                          "emaillcco":fatura.company_id.partner_id.email,
                          "assunto":fatura.company_id.edoc_nfe_email_subject,
                          "texto":fatura.company_id.edoc_nfe_email_text_send,
                          "anexapdf":"1"
                         })

            
            params = urllib.urlencode(dados)
            host = "http://%s:%s/ManagerAPIWeb/nfe/email" %(dados["ip"],dados["porta"])                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             
            response = requests.post(host,params=params,auth=(dados["usuario"],dados["senha"]))

            #EXCEPTION,EspdManNFeChaveNotFound,ChaveNota não foi informado
            self.log(cr, uid, 7, "Envio de email: Retorno=%s" % response.text)
                           
        return True
    
    def get_edoc_data(self, cr, uid, ids, context=None):
        user_obj = self.pool.get('res.users')
        user = user_obj.browse(cr, uid, uid)
        
        cnpj = user.company_id.partner_id.cnpj_cpf
        cnpj = cnpj.replace('.','').replace('/','').replace('-','')
        dados = {"grupo":user.company_id.edoc_group,
                 "cnpj":cnpj,
                 "usuario":user.company_id.edoc_user,
                 "senha":user.company_id.edoc_password,
                 "ip":user.company_id.edoc_host,
                 "porta":user.company_id.edoc_port
                 }
        
        return dados
    
    def return_max_batch_for_invoice(self, cr, uid, ids, context=None,fatura=None):
        batch_obj = self.pool.get('account.invoice.nfe.batch')
        cmd = "select id from account_invoice_nfe_batch where invoice_id= %s order by id desc limit 1" %(fatura.id)
        cr.execute(cmd) 
        reg = cr.fetchall()
        batch=None
        if reg:
            batch = batch_obj.browse(cr,uid,reg[0][0])     
        return batch
    
    def action_invoice_cancel_redir(self, cr, uid, ids, context=None):
        wf_service = netsvc.LocalService("workflow")
        fatura_obj = self.pool.get("account.invoice")
        faturas = fatura_obj.browse(cr, uid, ids)
        for fatura in faturas:
            if fatura.state=='open' and fatura.fiscal_document_nfe==True and \
             fatura.own_invoice==True:
                if context is None: 
                    context = {}
                wizard_id = self.pool.get("account.invoice.nfe.sefaz.cancel").create(cr, uid, {'justificativa':'<Informe a justificativa aqui>'}, context=dict(context, active_ids=ids))
                return {
                    'name':("Cancelamento de NF-e"),
                    'view_mode': 'form',
                    'view_id': False,
                    'view_type': 'form',
                    'res_model': 'account.invoice.nfe.sefaz.cancel',
                    'res_id':wizard_id,
                    'type': 'ir.actions.act_window',
                    'nodestroy': True,
                    'target': 'new',
                    'domain': '[]',
                    'context': dict(context, active_ids=ids)
                }
            else:
                wf_service.trg_validate(uid, 'account.invoice', fatura.id, 'invoice_cancel', cr)
        return True

    
#    def fields_view_get(self, cr, uid, view_id=None, view_type=False, context=None, toolbar=False, submenu=False):
#        result = super(invoice,self).fields_view_get(cr, uid, view_id=view_id, view_type=view_type, context=context, toolbar=toolbar, submenu=submenu)
#        if view_type=='form':
#            result['arch'] = result['arch'].replace(
#                '<button name="invoice_open" states="sefaz_export,proforma2" string="Validar" icon="gtk-go-forward" modifiers="{&quot;invisible&quot;: [[&quot;state&quot;, &quot;not in&quot;, [&quot;sefaz_export&quot;, &quot;proforma2&quot;]]]}"/>',
#                '''<button name="invoice_open" states="sefaz_export,proforma2" string="Validar" icon="gtk-go-forward" modifiers="{&quot;invisible&quot;: 0}"/>
#                   <button name="nfe_edoc_send" type="object" states="sefaz_export" string="Enviar Agora" icon="gtk-go-forward" modifiers="{&quot;invisible&quot;: [[&quot;state&quot;, &quot;not in&quot;, [&quot;sefaz_export&quot;]]]}"/>
#
#                '''
#                )
#        return result

    def request_for_edoc(self):
        pass
    
    def nfe_export_txt(self, cr, uid, ids, nfe_environment='1', context=False):
        StrFile = ''
        StrNF = 'NOTA FISCAL|%s|\n' % len(ids)
        StrFile = StrNF
        
        if nfe_environment: 
            nfe_environment='1'
        else: 
            nfe_environment='2' 
        
        for inv in self.browse(cr, uid, ids, context={'lang': 'pt_BR'}):
            #Endereço do company
            company_addr = self.pool.get('res.partner').address_get(cr, uid, [inv.company_id.partner_id.id], ['default'])
            company_addr_default = self.pool.get('res.partner.address').browse(cr, uid, [company_addr['default']], context={'lang': 'pt_BR'})[0]
            

            StrA = 'A|%s|%s|\n' % ('2.00', '')

            StrFile += StrA
            
            StrRegB = {
                       'cUF': company_addr_default.state_id.ibge_code,
                       'cNF': random.randint(10000000,999999999),
                       'NatOp': normalize('NFKD',unicode(inv.cfop_ids[0].small_name or '')).encode('ASCII','ignore'),
                       'intPag': '2', 
                       'mod': inv.fiscal_document_id.code,
                       'serie': inv.document_serie_id.code,
                       'nNF': inv.internal_number or '',
                       'dEmi': inv.date_invoice or '',
                       'dSaiEnt': inv.date_invoice or '',
                       'hSaiEnt': '',
                       'tpNF': '',
                       'cMunFG': ('%s%s') % (company_addr_default.state_id.ibge_code, company_addr_default.l10n_br_city_id.ibge_code),
                       'TpImp': '1',
                       'TpEmis': '1',
                       'cDV': '',
                       'tpAmb': nfe_environment,
                       'finNFe': '1',
                       'procEmi': '0',
                       'VerProc': '2.0.9',
                       'dhCont': '',
                       'xJust': '',
                       }

            if inv.cfop_ids[0].type in ("input"):
                StrRegB['tpNF'] = '0'
            else:
                StrRegB['tpNF'] = '1' 

            StrB = 'B|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|\n' % (StrRegB['cUF'], StrRegB['cNF'], StrRegB['NatOp'], StrRegB['intPag'], 
                                                                                 StrRegB['mod'], StrRegB['serie'], StrRegB['nNF'], StrRegB['dEmi'], StrRegB['dSaiEnt'],
                                                                                 StrRegB['hSaiEnt'], StrRegB['tpNF'], StrRegB['cMunFG'], StrRegB['TpImp'], StrRegB['TpEmis'],
                                                                                 StrRegB['cDV'], StrRegB['tpAmb'], StrRegB['finNFe'], StrRegB['procEmi'], StrRegB['VerProc'], 
                                                                                 StrRegB['dhCont'], StrRegB['xJust'])
            StrFile += StrB
            
            StrRegC = {
                       'XNome': normalize('NFKD',unicode(inv.company_id.partner_id.legal_name or '')).encode('ASCII','ignore'), 
                       'XFant': normalize('NFKD',unicode(inv.company_id.partner_id.name or '')).encode('ASCII','ignore'),
                       'IE': re.sub('[%s]' % re.escape(string.punctuation), '', inv.company_id.partner_id.inscr_est or ''),
                       'IEST': '',
                       'IM': re.sub('[%s]' % re.escape(string.punctuation), '', inv.company_id.partner_id.inscr_mun or ''),
                       'CNAE': re.sub('[%s]' % re.escape(string.punctuation), '', inv.company_id.cnae_main_id.code or ''),
                       'CRT': inv.company_id.fiscal_type or '',
                       }
            
            #TODO - Verificar, pois quando e informado do CNAE ele exige que a inscricao municipal, parece um bug do emissor da NFE
            if not inv.company_id.partner_id.inscr_mun:
                StrRegC['CNAE'] = ''
            
            StrC = 'C|%s|%s|%s|%s|%s|%s|%s|\n' % (StrRegC['XNome'], StrRegC['XFant'], StrRegC['IE'], StrRegC['IEST'], 
                                                StrRegC['IM'],StrRegC['CNAE'],StrRegC['CRT'])

            StrFile += StrC

            if inv.company_id.partner_id.tipo_pessoa == 'J':
                StrC02 = 'C02|%s|\n' % (re.sub('[%s]' % re.escape(string.punctuation), '', inv.company_id.partner_id.cnpj_cpf or ''))
            else:
                StrC02 = 'C02a|%s|\n' % (re.sub('[%s]' % re.escape(string.punctuation), '', inv.company_id.partner_id.cnpj_cpf or ''))

            StrFile += StrC02

            address_company_bc_code = ''
            if company_addr_default.country_id.bc_code:
                address_company_bc_code = company_addr_default.country_id.bc_code[1:]

            StrRegC05 = {
                       'XLgr': normalize('NFKD',unicode(company_addr_default.street or '')).encode('ASCII','ignore'), 
                       'Nro': company_addr_default.number or '',
                       'Cpl': normalize('NFKD',unicode(company_addr_default.street2 or '')).encode('ASCII','ignore'),
                       'Bairro': normalize('NFKD',unicode(company_addr_default.district or 'Sem Bairro')).encode('ASCII','ignore'),
                       'CMun': '%s%s' % (company_addr_default.state_id.ibge_code, company_addr_default.l10n_br_city_id.ibge_code),
                       'XMun':  normalize('NFKD',unicode(company_addr_default.l10n_br_city_id.name or '')).encode('ASCII','ignore'),
                       'UF': company_addr_default.state_id.code or '',
                       'CEP': re.sub('[%s]' %  re.escape(string.punctuation), '', str(company_addr_default.zip or '').replace(' ','')),
                       'cPais': address_company_bc_code or '',
                       'xPais': normalize('NFKD',unicode(company_addr_default.country_id.name or '')).encode('ASCII','ignore'),
                       'fone': re.sub('[%s]' % re.escape(string.punctuation), '', str(company_addr_default.phone or '').replace(' ','')),
                       }

            StrC05 = 'C05|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|\n' % (StrRegC05['XLgr'], StrRegC05['Nro'], StrRegC05['Cpl'], StrRegC05['Bairro'],
                                                                  StrRegC05['CMun'], StrRegC05['XMun'], StrRegC05['UF'], StrRegC05['CEP'],
                                                                  StrRegC05['cPais'], StrRegC05['xPais'], StrRegC05['fone'])

            StrFile += StrC05
            
            #Se o ambiente for de teste deve ser escrito na razão do destinatário
            if nfe_environment == '2': 
                xNome = 'NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL'
            else:
                xNome = normalize('NFKD', unicode(inv.partner_id.legal_name or '')).encode('ASCII', 'ignore')

            StrRegE = {
                       'xNome': xNome, 
                       'IE': re.sub('[%s]' % re.escape(string.punctuation), '', inv.partner_id.inscr_est or ''),
                       'ISUF': '',
                       'email': inv.partner_id.email or '',
                       }
            
            StrE = 'E|%s|%s|%s|%s|\n' % (StrRegE['xNome'], StrRegE['IE'], StrRegE['ISUF'], StrRegE['email'])

            StrFile += StrE

            if inv.partner_id.tipo_pessoa == 'J':
                StrE0 = 'E02|%s|\n' % (re.sub('[%s]' % re.escape(string.punctuation), '', inv.partner_id.cnpj_cpf or ''))
            else:
                StrE0 = 'E03|%s|\n' % (re.sub('[%s]' % re.escape(string.punctuation), '', inv.partner_id.cnpj_cpf or ''))

            StrFile += StrE0
            
            address_invoice_bc_code = ''
            if inv.address_invoice_id.country_id.bc_code:
                address_invoice_bc_code = inv.address_invoice_id.country_id.bc_code[1:]

            StrRegE05 = {
                       'xLgr': normalize('NFKD',unicode(inv.address_invoice_id.street or '')).encode('ASCII','ignore'),
                       'nro': normalize('NFKD',unicode(inv.address_invoice_id.number or '')).encode('ASCII','ignore'),
                       'xCpl': re.sub('[%s]' % re.escape(string.punctuation), '', normalize('NFKD',unicode(inv.address_invoice_id.street2 or '' )).encode('ASCII','ignore')),
                       'xBairro': normalize('NFKD',unicode(inv.address_invoice_id.district or 'Sem Bairro')).encode('ASCII','ignore'),
                       'cMun': ('%s%s') % (inv.address_invoice_id.state_id.ibge_code, inv.address_invoice_id.l10n_br_city_id.ibge_code),
                       'xMun': normalize('NFKD',unicode(inv.address_invoice_id.l10n_br_city_id.name or '')).encode('ASCII','ignore'),
                       'UF': inv.address_invoice_id.state_id.code,
                       'CEP': re.sub('[%s]' % re.escape(string.punctuation), '', str(inv.address_invoice_id.zip or '').replace(' ','')),
                       'cPais': address_invoice_bc_code,
                       'xPais': normalize('NFKD',unicode(inv.address_invoice_id.country_id.name or '')).encode('ASCII','ignore'),
                       'fone': re.sub('[%s]' % re.escape(string.punctuation), '', str(inv.address_invoice_id.phone or '').replace(' ','')),
                       }
            
            StrE05 = 'E05|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|\n' % (StrRegE05['xLgr'], StrRegE05['nro'], StrRegE05['xCpl'], StrRegE05['xBairro'],
                                                           StrRegE05['cMun'], StrRegE05['xMun'], StrRegE05['UF'], StrRegE05['CEP'],
                                                           StrRegE05['cPais'],StrRegE05['xPais'], StrRegE05['fone'],)
            
            StrFile += StrE05
            
            if inv.partner_shipping_id:
                
                if inv.address_invoice_id != inv.partner_shipping_id: 
            
                    StrRegG = {
                               'XLgr': normalize('NFKD',unicode(inv.partner_shipping_id.street or '',)).encode('ASCII','ignore'),
                               'Nro': normalize('NFKD',unicode(inv.partner_shipping_id.number or '')).encode('ASCII','ignore'),
                               'XCpl': re.sub('[%s]' % re.escape(string.punctuation), '', normalize('NFKD',unicode(inv.partner_shipping_id.street2 or '' )).encode('ASCII','ignore')),
                               'XBairro': re.sub('[%s]' % re.escape(string.punctuation), '', normalize('NFKD',unicode(inv.partner_shipping_id.district or 'Sem Bairro' )).encode('ASCII','ignore')),
                               'CMun': ('%s%s') % (inv.partner_shipping_id.state_id.ibge_code, inv.partner_shipping_id.l10n_br_city_id.ibge_code),
                               'XMun': normalize('NFKD',unicode(inv.partner_shipping_id.l10n_br_city_id.name or '')).encode('ASCII','ignore'),
                               'UF': inv.address_invoice_id.state_id.code,
                             }
          
                    StrG = 'G|%s|%s|%s|%s|%s|%s|%s|\n' % (StrRegG['XLgr'],StrRegG['Nro'],StrRegG['XCpl'],StrRegG['XBairro'],StrRegG['CMun'],StrRegG['XMun'],StrRegG['UF'])
                    StrFile += StrG
                    
                    if inv.partner_id.tipo_pessoa == 'J':
                        StrG0 = 'G02|%s|\n' % (re.sub('[%s]' % re.escape(string.punctuation), '', inv.partner_id.cnpj_cpf or ''))
                    else:
                        StrG0 = 'G02a|%s|\n' % (re.sub('[%s]' % re.escape(string.punctuation), '', inv.partner_id.cnpj_cpf or ''))
        
                    StrFile += StrG0
            
            i = 0
            for inv_line in inv.invoice_line:
                i += 1
            
                StrH = 'H|%s||\n' % (i)
                
                
                StrFile += StrH

                decimal_precision_obj = self.pool.get('decimal.precision')
                ids = decimal_precision_obj.search(cr, uid, [('name', '=', 'Account unit price')])
                


               
                StrRegI = {
                       'CProd': normalize('NFKD',unicode(inv_line.product_id.code or '',)).encode('ASCII','ignore'),
                       'CEAN': inv_line.product_id.ean13 or '',
                       'XProd': normalize('NFKD',unicode(inv_line.product_id.name or '')).encode('ASCII','ignore'),
                       'NCM': re.sub('[%s]' % re.escape(string.punctuation), '', inv_line.product_id.property_fiscal_classification.name or ''),
                       'EXTIPI': '',
                       'CFOP': inv_line.cfop_id.code,
                       'UCom': normalize('NFKD',unicode(inv_line.uos_id.name or '',)).encode('ASCII','ignore'),
                       'QCom': str("%.4f" % inv_line.quantity),
                       'VUnCom': str("%.4f" % (inv_line.price_unit * (1-(inv_line.discount or 0.0)/100.0))),
                       'VProd': str("%.2f" % inv_line.price_total),
                       'CEANTrib': inv_line.product_id.ean13 or '',
                       'UTrib': inv_line.uos_id.name,
                       'QTrib': str("%.4f" % inv_line.quantity),
                       'VUnTrib': str("%.4f" % inv_line.price_unit),
                       'VFrete': '',
                       'VSeg': '',
                       'VDesc': '',
                       'vOutro': '',
                       'indTot': '1',
                       'xPed': '',
                       'nItemPed': '',
                       }

                if inv_line.product_id.code:
                    StrRegI['CProd'] = inv_line.product_id.code
                else:
                    StrRegI['CProd'] = unicode(i).strip().rjust(4, u'0')

                #No OpenERP já traz o valor unitário como desconto
                #if inv_line.discount > 0:
                #    StrRegI['VDesc'] = str("%.2f" % (inv_line.quantity * (inv_line.price_unit * (1-(inv_line.discount or 0.0)/100.0))))

                StrI = 'I|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|\n' % (StrRegI['CProd'], StrRegI['CEAN'], StrRegI['XProd'], StrRegI['NCM'],
                                                                                          StrRegI['EXTIPI'], StrRegI['CFOP'], StrRegI['UCom'], StrRegI['QCom'], 
                                                                                          StrRegI['VUnCom'], StrRegI['VProd'], StrRegI['CEANTrib'], StrRegI['UTrib'],
                                                                                          StrRegI['QTrib'], StrRegI['VUnTrib'], StrRegI['VFrete'], StrRegI['VSeg'],
                                                                                          StrRegI['VDesc'], StrRegI['vOutro'], StrRegI['indTot'], StrRegI['xPed'],
                                                                                          StrRegI['nItemPed'])
                
                StrFile += StrI
                
                StrM = 'M|\n'
                
                StrFile += StrM
                
                StrN = 'N|\n'
         
                StrFile += StrN

                #TODO - Fazer alteração para cada tipo de cst
                if inv_line.icms_cst in ('00'):
                    
                    StrRegN02 = {
                       'Orig': inv_line.product_id.origin or '0',
                       'CST': inv_line.icms_cst,
                       'ModBC': '0',
                       'VBC': str("%.2f" % inv_line.icms_base),
                       'PICMS': str("%.2f" % inv_line.icms_percent),
                       'VICMS': str("%.2f" % inv_line.icms_value),
                       }
                
                    StrN02 = 'N02|%s|%s|%s|%s|%s|%s|\n' % (StrRegN02['Orig'], StrRegN02['CST'], StrRegN02['ModBC'], StrRegN02['VBC'], StrRegN02['PICMS'],
                                                     StrRegN02['VICMS'])
                    
                    StrFile += StrN02
                
                if inv_line.icms_cst in ('20'):

                    StrRegN04 = {
                       'Orig': inv_line.product_id.origin or '0',
                       'CST': inv_line.icms_cst,
                       'ModBC': '0',
                       'PRedBC': str("%.2f" % inv_line.icms_percent_reduction),
                       'VBC': str("%.2f" % inv_line.icms_base),
                       'PICMS': str("%.2f" % inv_line.icms_percent),
                       'VICMS': str("%.2f" % inv_line.icms_value),
                       }
                
                    StrN04 = 'N04|%s|%s|%s|%s|%s|%s|%s|\n' % (StrRegN04['Orig'], StrRegN04['CST'], StrRegN04['ModBC'], StrRegN04['PRedBC'], StrRegN04['VBC'], StrRegN04['PICMS'],
                                                              StrRegN04['VICMS'])
                    StrFile += StrN04
                
                if inv_line.icms_cst in ('10'):
                    StrRegN03 = {
                       'Orig': inv_line.product_id.origin or '0',
                       'CST': inv_line.icms_cst,
                       'ModBC': '0',
                       'VBC': str("%.2f" % inv_line.icms_base),
                       'PICMS': str("%.2f" % inv_line.icms_percent),
                       'VICMS': str("%.2f" % inv_line.icms_value),
                       'ModBCST': '4', #TODO
                       'PMVAST': str("%.2f" % inv_line.icms_st_mva) or '',
                       'PRedBCST': '',
                       'VBCST': str("%.2f" % inv_line.icms_st_base),
                       'PICMSST': str("%.2f" % inv_line.icms_st_percent),
                       'VICMSST': str("%.2f" % inv_line.icms_st_value),
                       }

                    StrN03 = 'N03|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|\n' % (StrRegN03['Orig'], StrRegN03['CST'], StrRegN03['ModBC'], StrRegN03['VBC'], StrRegN03['PICMS'],
                    StrRegN03['VICMS'], StrRegN03['ModBCST'], StrRegN03['PMVAST'], StrRegN03['PRedBCST'], StrRegN03['VBCST'],
                    StrRegN03['PICMSST'], StrRegN03['VICMSST'])
                    StrFile += StrN03
                    
                if inv_line.icms_cst in ('40', '41', '50', '51'):
                    StrRegN06 = {
                       'Orig': inv_line.product_id.origin or '0',
                       'CST': inv_line.icms_cst,
                       'vICMS': str("%.2f" % inv_line.icms_value),
                       'motDesICMS': '9', #FIXME
                       }
                
                    StrN06 = 'N06|%s|%s|%s|%s|\n' % (StrRegN06['Orig'], StrRegN06['CST'], StrRegN06['vICMS'], StrRegN06['motDesICMS'])
                    
                    StrFile += StrN06
                
                if inv_line.icms_cst in ('60'):                    
                    StrRegN08 = {
                       'Orig': inv_line.product_id.origin or '0',
                       'CST': inv_line.icms_cst,
                       'VBCST': str("%.2f" % 0.00),
                       'VICMSST': str("%.2f" % 0.00),
                       }

                    StrN08 = 'N08|%s|%s|%s|%s|\n' % (StrRegN08['Orig'], StrRegN08['CST'], StrRegN08['VBCST'], StrRegN08['VICMSST'])
                    
                    StrFile += StrN08
                    
                if inv_line.icms_cst in ('70'):
                    StrRegN09 = {
                       'Orig': inv_line.product_id.origin or '0',
                       'CST': inv_line.icms_cst,
                       'ModBC': '0',
                       'PRedBC': str("%.2f" % inv_line.icms_percent_reduction),
                       'VBC': str("%.2f" % inv_line.icms_base),
                       'PICMS': str("%.2f" % inv_line.icms_percent),
                       'VICMS': str("%.2f" % inv_line.icms_value),
                       'ModBCST': '4', #TODO
                       'PMVAST': str("%.2f" % inv_line.icms_st_mva) or '',
                       'PRedBCST': '',
                       'VBCST': str("%.2f" % inv_line.icms_st_base),
                       'PICMSST': str("%.2f" % inv_line.icms_st_percent),
                       'VICMSST': str("%.2f" % inv_line.icms_st_value),
                       }
                
                    StrN09 = 'N09|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|\n' % (StrRegN09['Orig'], StrRegN09['CST'], StrRegN09['ModBC'], StrRegN09['PRedBC'], StrRegN09['VBC'], StrRegN09['PICMS'], StrRegN09['VICMS'], StrRegN09['ModBCST'], StrRegN09['PMVAST'], StrRegN09['PRedBCST'], StrRegN09['VBCST'], StrRegN09['PICMSST'], StrRegN09['VICMSST'])

                    StrFile += StrN09
                    

		if inv_line.icms_cst in ('101'):
                    StrRegN10c = {
                       'Orig': inv_line.product_id.origin or '0',
                       'CSOSN': inv_line.icms_cst,
		               'pCredSN': str('%.2f' % inv_line.icms_percent),
		               'vCredICMSSN': str('%.2f' % inv_line.icms_value),
                       }      
                        
                    
                    StrN10c = 'N10c|%s|%s|%s|%s|\n' % (StrRegN10c['Orig'],StrRegN10c['CSOSN'],StrRegN10c['pCredSN'],StrRegN10c['vCredICMSSN'])
                    StrFile += StrN10c

                if inv_line.icms_cst in ('400','102'):
                    StrRegN10d = {
                       'Orig': inv_line.product_id.origin or '0',
                       'CST': inv_line.icms_cst,
                       }      
                        
                    
                    StrN10d = 'N10d|%s|%s|\n' % (StrRegN10d['Orig'],StrRegN10d['CST'])
                    StrFile += StrN10d
                     
                if inv_line.icms_cst in ('90', '900'):
                    StrRegN10h = {
                                  'Orig': inv_line.product_id.origin or '0',
                                  'CSOSN': inv_line.icms_cst,
                                  'modBC': '0',
                                  'vBC': str("%.2f" % 0.00),
                                  'pRedBC': '',
                                  'pICMS': str("%.2f" % 0.00),
                                  'vICMS': str("%.2f" % 0.00),
                                  'modBCST': '',
                                  'pMVAST': '',
                                  'pRedBCST': '',
                                  'vBCST': '',
                                  'pICMSST': '',
                                  'vICMSST': '',
                                  'pCredSN': str("%.2f" % 0.00),
                                  'vCredICMSSN': str("%.2f" % 0.00),
                                  }
                                    
                    StrN10h = 'N10h|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|\n' % (StrRegN10h['Orig'], 
                                                                                        StrRegN10h['CSOSN'], 
                                                                                        StrRegN10h['modBC'],
                                                                                        StrRegN10h['vBC'],
                                                                                        StrRegN10h['pRedBC'],
                                                                                        StrRegN10h['pICMS'],
                                                                                        StrRegN10h['vICMS'],
                                                                                        StrRegN10h['modBCST'],
                                                                                        StrRegN10h['pMVAST'],
                                                                                        StrRegN10h['pRedBCST'],
                                                                                        StrRegN10h['vBCST'],
                                                                                        StrRegN10h['pICMSST'],
                                                                                        StrRegN10h['vICMSST'],
                                                                                        StrRegN10h['pCredSN'],
                                                                                        StrRegN10h['vCredICMSSN'])
                    StrFile += StrN10h

                StrRegO = {
                       'ClEnq': '',
                       'CNPJProd': '',
                       'CSelo': '',
                       'QSelo': '',
                       'CEnq': '999',
                }
                
                StrO = 'O|%s|%s|%s|%s|%s|\n' % (StrRegO['ClEnq'], StrRegO['CNPJProd'], StrRegO['CSelo'], StrRegO['QSelo'], StrRegO['CEnq']) 
                
                StrFile += StrO

                if inv_line.ipi_cst in ('50', '51', '52') and inv_line.ipi_percent > 0:
                    StrRegO07 = {
                       'CST': inv_line.ipi_cst,
                       'VIPI': str("%.2f" % inv_line.ipi_value),
                    }
                    
                    StrO07 = 'O07|%s|%s|\n' % (StrRegO07['CST'], StrRegO07['VIPI'])
                    
                    StrFile += StrO07 

                    if inv_line.ipi_type == 'percent' or '':
                        StrRegO10 = {
                           'VBC': str("%.2f" % inv_line.ipi_base),
                           'PIPI': str("%.2f" % inv_line.ipi_percent),
                        }
                        StrO1 = 'O10|%s|%s|\n' % (StrRegO10['VBC'], StrRegO10['PIPI'])
                    
                    if inv_line.ipi_type == 'quantity':
                        pesol = 0
                        if inv_line.product_id:
                            pesol = inv_line.product_id.weight_net
                        StrRegO11 = {
                           'QUnid': str("%.4f" % (inv_line.quantity * pesol)),
                           'VUnid': str("%.4f" % inv_line.ipi_percent),
                        }
                        StrO1 = 'O11|%s|%s|\n' % (StrRegO11['QUnid'], StrRegO11['VUnid'])
                    
                    StrFile += StrO1
                
                if inv_line.ipi_cst in ('99'):
                    StrRegO07 = {
                                 'CST': inv_line.ipi_cst,
                                 'VIPI': str("%.2f" % inv_line.ipi_value),
                                 }
                    
                    StrO07 = ('O07|%s|%s|\n') % (StrRegO07['CST'], StrRegO07['VIPI'])
                    StrFile += StrO07
                    
                    StrRegO10 = {
                                 'VBC': str("%.2f" % inv_line.ipi_base),
                                 'PIPI': str("%.2f" % inv_line.ipi_percent),
                                 }
                    
                    StrO10 = ('O10|%s|%s|\n') % (StrRegO10['VBC'], StrRegO10['PIPI'])
                    StrFile += StrO10
                    
                if inv_line.ipi_percent == 0 and not inv_line.ipi_cst in ('99'):
                    StrO1 = 'O08|%s|\n' % inv_line.ipi_cst
                    StrFile += StrO1
                    
                StrQ = 'Q|\n'
                
                StrFile += StrQ
                    
                if inv_line.pis_cst in ('01') and inv_line.pis_percent > 0:
                    StrRegQ02 = {
                                 'CST': inv_line.pis_cst,
                                 'VBC': str("%.2f" % inv_line.pis_base),
                                 'PPIS': str("%.2f" % inv_line.pis_percent),
                                 'VPIS': str("%.2f" % inv_line.pis_value),
                                 }
                    
                    StrQ02 = ('Q02|%s|%s|%s|%s|\n') % (StrRegQ02['CST'], 
                                                       StrRegQ02['VBC'], 
                                                       StrRegQ02['PPIS'], 
                                                       StrRegQ02['VPIS'])
                    
                    StrFile += StrQ02
                    
                if inv_line.pis_cst in ('49','99'):
                    StrRegQ05 = {
                                 'CST': inv_line.pis_cst,
                                 'VPIS': str("%.2f" % inv_line.pis_value),
                                 }
                    
                    StrQ05 = ('Q05|%s|%s|\n') % (StrRegQ05['CST'], StrRegQ05['VPIS'])
                    StrFile += StrQ05
                    
                    StrRegQ07 = {
                                 'VBC': str("%.2f" % inv_line.pis_base),
                                 'PPIS': str("%.2f" % inv_line.pis_percent),
                                 }
                    
                    StrQ07 = ('Q07|%s|%s|\n') % (StrRegQ07['VBC'], StrRegQ07['PPIS'])
                    StrFile += StrQ07
                    
                if inv_line.pis_percent == 0 and not inv_line.pis_cst in ('49','99'):
                    StrQ04 = 'Q04|%s|\n' % (inv_line.pis_cst)
                    StrFile += StrQ04
                
                StrQ = 'S|\n'
                
                StrFile += StrQ

                if inv_line.cofins_cst in ('01') and inv_line.cofins_percent > 0:
                    StrRegS02 = {
                       'CST': inv_line.cofins_cst,
                       'VBC': str("%.2f" % inv_line.cofins_base),
                       'PCOFINS': str("%.2f" % inv_line.cofins_percent),
                       'VCOFINS': str("%.2f" % inv_line.cofins_value),
                    }

                    StrS02 = ('S02|%s|%s|%s|%s|\n') % (StrRegS02['CST'], StrRegS02['VBC'], StrRegS02['PCOFINS'], StrRegS02['VCOFINS'])
                    StrFile += StrS02
                    
                if inv_line.cofins_cst in ('49','99'):
                    StrRegS05 = {
                                 'CST': inv_line.cofins_cst,
                                 'VCOFINS': str("%.2f" % inv_line.cofins_value),
                                 }
                    
                    StrS05 = ('S05|%s|%s|\n') % (StrRegS05['CST'], StrRegS05['VCOFINS'])
                    StrFile += StrS05
                    
                    StrRegS07 = {
                                 'VBC': str("%.2f" % inv_line.cofins_base),
                                 'PCOFINS': str("%.2f" % inv_line.cofins_percent),
                                 }
                    
                    StrS07 = ('S07|%s|%s|\n') % (StrRegS07['VBC'], StrRegS07['PCOFINS'])
                    StrFile += StrS07
                        
            if inv_line.cofins_percent == 0 and not inv_line.cofins_cst in ('49','99'):
                StrS02 = 'S04|%s|\n' % inv_line.cofins_cst
                StrFile += StrS02
                
            StrW = 'W|\n'
            
            StrFile += StrW
	    

            if inv_line.company_id.partner_id.partner_fiscal_type_id.code != "Simples Nacional":
                StrRegW02 = {
                     'vBC': str("%.2f" % inv.icms_base),
                     'vICMS': str("%.2f" % inv.icms_value),
                     'vBCST': str("%.2f" % inv.icms_st_base),
                     'vST': str("%.2f" % inv.icms_st_value),
                     'vProd': str("%.2f" % inv.amount_untaxed),
                     'vFrete': str("%.2f" % inv.amount_freight),
                     'vSeg': str("%.2f" % inv.amount_insurance),
                     'vDesc': '0.00',
                     'vII': '0.00',
                     'vIPI': str("%.2f" % inv.ipi_value),
                     'vPIS': str("%.2f" % inv.pis_value),
                     'vCOFINS': str("%.2f" % inv.cofins_value),
                     'vOutro': str("%.2f" % inv.amount_costs),
                     'vNF': str("%.2f" % inv.amount_total),
                     }
            else:
                StrRegW02 = {
                             'vBC':  '0.00',
                             'vICMS': '0.00',
                             'vBCST':  '0.00',
                             'vST':  '0.00',
                             'vProd': str("%.2f" % inv.amount_untaxed),
                             'vFrete': str("%.2f" % inv.amount_freight),
                             'vSeg': str("%.2f" % inv.amount_insurance),
                             'vDesc': '0.00',
                             'vII': '0.00',
                             'vIPI': '0.00',
                             'vPIS': str("%.2f" % inv.pis_value),
                             'vCOFINS': str("%.2f" % inv.cofins_value),
                             'vOutro': str("%.2f" % inv.amount_costs),
                             'vNF': str("%.2f" % inv.amount_total),
                             }
	
            
            StrW02 = 'W02|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s\n' % ( StrRegW02['vBC'],StrRegW02['vICMS'], StrRegW02['vBCST'], StrRegW02['vST'], StrRegW02['vProd'],
                                                                         StrRegW02['vFrete'], StrRegW02['vSeg'], StrRegW02['vDesc'], StrRegW02['vII'], StrRegW02['vIPI'],
                                                                         StrRegW02['vPIS'], StrRegW02['vCOFINS'], StrRegW02['vOutro'], StrRegW02['vNF'])
            
            StrFile += StrW02
            
            # Modo do Frete: 0- Por conta do emitente; 1- Por conta do destinatário/remetente; 2- Por conta de terceiros; 9- Sem frete (v2.0)
            if not inv.incoterm:
                StrRegX0 = '9'
            else:
                StrRegX0 = inv.incoterm.freight_responsibility                      

            StrX = 'X|%s|\n' % (StrRegX0)
            
            StrFile += StrX
            
            StrRegX03 = {
                      'XNome': '',
                      'IE': '',
                      'XEnder': '',
                      'UF': '',
                      'XMun': '',
                      }
            
            StrX0 = ''
            
            if inv.carrier_id:            
            
                #Endereço da transportadora
                carrier_addr = self.pool.get('res.partner').address_get(cr, uid, [inv.carrier_id.partner_id.id], ['default'])
                carrier_addr_default = self.pool.get('res.partner.address').browse(cr, uid, [carrier_addr['default']])[0]
                
                if inv.carrier_id.partner_id.legal_name:
                    StrRegX03['XNome'] = normalize('NFKD', unicode(inv.carrier_id.partner_id.legal_name or '')).encode('ASCII', 'ignore')
                else:
                    StrRegX03['XNome'] = normalize('NFKD', unicode(inv.carrier_id.partner_id.name or '')).encode('ASCII', 'ignore')
                
                StrRegX03['IE'] = inv.carrier_id.partner_id.inscr_est or ''
                StrRegX03['XEnder'] = normalize('NFKD', unicode(carrier_addr_default.street or '')).encode('ASCII', 'ignore')
                StrRegX03['UF'] = carrier_addr_default.state_id.code or ''
                
                if carrier_addr_default.l10n_br_city_id:
                    StrRegX03['XMun'] = normalize('NFKD', unicode(carrier_addr_default.l10n_br_city_id.name or '')).encode('ASCII', 'ignore')
                
                if inv.carrier_id.partner_id.tipo_pessoa == 'J':
                    StrX0 = 'X04|%s|\n' %  (re.sub('[%s]' % re.escape(string.punctuation), '', inv.carrier_id.partner_id.cnpj_cpf or ''))
                else:
                    StrX0 = 'X05|%s|\n' %  (re.sub('[%s]' % re.escape(string.punctuation), '', inv.carrier_id.partner_id.cnpj_cpf or ''))

            StrX03 = 'X03|%s|%s|%s|%s|%s|\n' % (StrRegX03['XNome'], StrRegX03['IE'], StrRegX03['XEnder'], StrRegX03['UF'], StrRegX03['XMun'])

            StrFile += StrX03
            StrFile += StrX0

            StrRegX18 = {
                         'Placa': '',
                         'UF': '',
                         'RNTC': '',
                         }

            if inv.vehicle_id:
                StrRegX18['Placa'] = inv.vehicle_id.plate or ''
                StrRegX18['UF'] = inv.vehicle_id.plate.state_id.code or ''
                StrRegX18['RNTC'] = inv.vehicle_id.rntc_code or ''
                         

            StrX18 = 'X18|%s|%s|%s|\n' % (StrRegX18['Placa'], StrRegX18['UF'], StrRegX18['RNTC'])

            StrFile += StrX18

            StrRegX26 = {
                         'QVol': '',
                         'Esp': '', 
                         'Marca': '',
                         'NVol': '',
                         'PesoL': '',
                         'PesoB': '',
                         }

            if inv.number_of_packages:
                StrRegX26['QVol'] = inv.number_of_packages
                StrRegX26['Esp'] = 'Volume' #TODO
                StrRegX26['Marca']
                StrRegX26['NVol']
                StrRegX26['PesoL'] = str("%.3f" % inv.weight_net)
                StrRegX26['PesoB'] = str("%.3f" % inv.weight)

            StrX26 = 'X26|%s|%s|%s|%s|%s|%s|\n' % (StrRegX26['QVol'], StrRegX26['Esp'], StrRegX26['Marca'], StrRegX26['NVol'], StrRegX26['PesoL'], StrRegX26['PesoB'])

            StrFile += StrX26
            
            
            if not inv.payment_term: 
                if inv.date_due:
                    StrY = 'Y|\n'
                    StrFile += StrY
                    
                    StrRegY07 = {
                           'NDup': '%s' % inv.internal_number,
                           'DVenc': inv.date_due,
                           'VDup': str("%.2f" % inv.amount_total),
                           }
                    
                    StrY07 = 'Y07|%s|%s|%s|\n' % (StrRegY07['NDup'], StrRegY07['DVenc'], StrRegY07['VDup'])
                    
                    StrFile += StrY07
                
            elif inv.journal_id.revenue_expense:
            
                StrY = 'Y|\n'
                
                StrFile += StrY
                
                for line in inv.move_line_receivable_id:
                    StrRegY07 = {
                       'NDup': line.name,
                       'DVenc': line.date_maturity or inv.date_due or inv.date_invoice,
                       'VDup': str("%.2f" % line.debit),
                       }
                
                    StrY07 = 'Y07|%s|%s|%s|\n' % (StrRegY07['NDup'], StrRegY07['DVenc'], StrRegY07['VDup'])
                    
                    StrFile += StrY07
                    
            comment = ''       
            if inv.comment:
                comment = inv.comment.replace('\n',' ')        
            StrRegZ = {
                       'InfAdFisco': '',
                       'InfCpl': normalize('NFKD',unicode(comment or '')).encode('ASCII','ignore'),
                       }
            
            StrZ = 'Z|%s|%s|\n' % (StrRegZ['InfAdFisco'], StrRegZ['InfCpl'])

            StrFile += StrZ              
            
            self.write(cr, uid, [inv.id], {'nfe_export_date': datetime.now()})

        return unicode(StrFile.encode('utf-8'), errors='replace')
    
    
invoice()




class nfe_inutiliza(osv.osv):
    _name="account.invoice.nfe.sefaz.inutiliza"
    _columns={
              'ano': fields.integer('Ano',size=2,required=True),
              'serie': fields.many2one('l10n_br_account.document.serie',
                                        'Serie'),
              'faixaini': fields.integer('Faixa inicial',size=6,required=True),
              'faixafim': fields.integer('Faixa final',size=6,required=True),
              'justificativa': fields.char('Justificativa',size=255,required=True),
              'state':fields.selection(
                                       [('draft','Rascunho'),
                                        ('done','Confirmado')
                                       ])
              }
    _defaults={
              'ano':13,
              'state':'draft'
              }
    
    def do_nfe_inutiliza(self, cr, uid, ids, context=None):

        inu_obj = self.pool.get('account.invoice.nfe.sefaz.inutiliza')
        inutilizacao = inu_obj.browse(cr, uid, ids)[0]
        fatura_obj = self.pool.get('account.invoice')
        

        dados = fatura_obj.get_edoc_data(cr, uid, ids)
        dados.update({"ano": inutilizacao.ano,
                      "serie":inutilizacao.serie.code,
                      "nfini":inutilizacao.faixaini,
                      "nffin":inutilizacao.faixafim,
                      "justificativa":inutilizacao.justificativa,
                      })

            
        params = urllib.urlencode(dados)
        host = "http://%s:%s/ManagerAPIWeb/nfe/inutiliza" %(dados["ip"],dados["porta"])                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             
        response = requests.post(host,params=params,auth=(dados["usuario"],dados["senha"]))

        list_response = response.text.split("|")
           
        self.log(cr, uid, 8, "Inutilizacao: Retorno=%s" % response.text)
        if list_response[0] == "EXCEPTION":
            raise osv.except_osv("Erro", list_response[2])
        return True
        
nfe_inutiliza()  

class nfe_email(osv.osv):
    _name="account.nfe.email"
    _description="Email de NF-e"
    _inherit="mail.thread"
    _rec_name="id"

    def teste(self,cr,uid,ids,context=None):
        nota = """<?xml version="1.0" encoding="utf-8"?>
                    <nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="2.00">
	                    <NFe xmlns="http://www.portalfiscal.inf.br/nfe"><infNFe versao="2.00" Id="NFe42130608365290000189550020000016231328725352"><ide><cUF>42</cUF><cNF>32872535</cNF><natOp>REMESSA PARA INDUSTRIALIZACAO POR ENCOMENDA</natOp><indPag>0</indPag><mod>55</mod><serie>2</serie><nNF>1623</nNF><dEmi>2013-06-13</dEmi><dSaiEnt>2013-06-13</dSaiEnt><tpNF>1</tpNF><cMunFG>4208906</cMunFG><tpImp>2</tpImp><tpEmis>1</tpEmis><cDV>2</cDV><tpAmb>1</tpAmb><finNFe>1</finNFe><procEmi>0</procEmi><verProc>1.0.6.8</verProc></ide><emit><CNPJ>08365290000189</CNPJ><xNome>FORMAFORMA INDUSTRIA METALURGICA LTDA</xNome><xFant>FORMAFORMA</xFant><enderEmit><xLgr>RUA BRUNO KITZBERGER, 30 SALA 01</xLgr><nro>2343</nro><xCpl>SALA 01</xCpl><xBairro>AGUA VERDE</xBairro><cMun>4208906</cMun><xMun>JARAGUA DO SUL</xMun><UF>SC</UF><CEP>89254420</CEP><cPais>1058</cPais><xPais>BRASIL</xPais><fone>33765100</fone></enderEmit><IE>255276559</IE><CRT>3</CRT></emit><dest><CNPJ>95806345000143</CNPJ><xNome>LUZMAR SERVICOS DE TORNO LTDA ME</xNome><enderDest><xLgr>AV. PREFEITO WALDEMAR GRUBBA</xLgr><nro>4955</nro><xCpl>BOX 1 E 2 PROXIMO PORTAL SHOPPING</xCpl><xBairro>VIEIRAS</xBairro><cMun>4208906</cMun><xMun>JARAGUA DO SUL</xMun><UF>SC</UF><CEP>89256501</CEP><cPais>1058</cPais><xPais>BRASIL</xPais></enderDest><IE>255084790</IE><email>luzmar.usinagem@terra.com.br</email></dest><det nItem="1"><prod><cProd>1.01.05.020</cProd><cEAN></cEAN><xProd>CANTONEIRA DE ACO 1020 38 X 2.12 POL.</xProd><NCM>72162100</NCM><CFOP>5901</CFOP><uCom>KG</uCom><qCom>14.0000</qCom><vUnCom>2.2838</vUnCom><vProd>31.97</vProd><cEANTrib></cEANTrib><uTrib>KG</uTrib><qTrib>14.0000</qTrib><vUnTrib>2.2838</vUnTrib><indTot>1</indTot></prod><imposto><ICMS><ICMS40><orig>0</orig><CST>50</CST></ICMS40></ICMS><IPI><cEnq>999</cEnq><IPINT><CST>53</CST></IPINT></IPI><PIS><PISNT><CST>07</CST></PISNT></PIS><COFINS><COFINSNT><CST>07</CST></COFINSNT></COFINS></imposto></det><total><ICMSTot><vBC>0.00</vBC><vICMS>0.00</vICMS><vBCST>0.00</vBCST><vST>0.00</vST><vProd>31.97</vProd><vFrete>0.00</vFrete><vSeg>0.00</vSeg><vDesc>0.00</vDesc><vII>0.00</vII><vIPI>0.00</vIPI><vPIS>0.00</vPIS><vCOFINS>0.00</vCOFINS><vOutro>0.00</vOutro><vNF>31.97</vNF></ICMSTot></total><transp><modFrete>1</modFrete></transp><infAdic><infCpl>ICMS SUSPENSAO DO ICMS CONF.ART.27INCISO I ANEXO 2 DO DECRETO 2.8702001.IPI SUSPENSAO DO IPI CONF.ART.43 INCISO VI DO DECRETO 7.21210. REMESSA QUE SEGUE PARA INDUSTRIALIZACAO COM POSTERIOR RETORNO. ICMS SUSPENSO RICMSSC ANEXO 2 ART. 27 I.</infCpl></infAdic></infNFe><Signature xmlns="http://www.w3.org/2000/09/xmldsig#"><SignedInfo><CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/><SignatureMethod Algorithm="http://www.w3.org/2000/09/xmldsig#rsa-sha1"/><Reference URI="#NFe42130608365290000189550020000016231328725352"><Transforms><Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"/><Transform Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/></Transforms><DigestMethod Algorithm="http://www.w3.org/2000/09/xmldsig#sha1"/><DigestValue>SPtoZ9foKO3Td8nn0dv8yK+tvyc=</DigestValue></Reference></SignedInfo><SignatureValue>T2mj3zsIhj1RWT7419qO6JYSMHfaB4admqpPWPBgkzrmXwOnrymHhb0fxZ1nkUmB7AHzvcipZM3XHsStmc89fny5NwPjBZwKP+nBEXusIzTGTR5VwcgSIcY9LeUGt7KnRD8bhEvdaFkEQrLTtLlpvxsTuPrX4kuH5AYyl4mhL3yn3oqsUBHj6FliDiXNnGdjN2fOZlm5EA9qJh4S5i5gKMPtEEe4i3uSHdnheZ+TtTXGn5tiyEfxP/YtuvgOjmd3mtB2YDMvUm4REHaCV4fZovQMeM6v5AQN3dLohRQR6t6eZLUJOUuMyz4J8NBO1p2KlKxk5pJNall0FoCGj0NTYA==</SignatureValue><KeyInfo><X509Data><X509Certificate>MIIIezCCBmOgAwIBAgIQekeDhtEHghDt7fUKIim8+TANBgkqhkiG9w0BAQsFADCBgDELMAkGA1UEBhMCQlIxEzARBgNVBAoTCklDUC1CcmFzaWwxNjA0BgNVBAsTLVNlY3JldGFyaWEgZGEgUmVjZWl0YSBGZWRlcmFsIGRvIEJyYXNpbCAtIFJGQjEkMCIGA1UEAxMbQUMgSW5zdGl0dXRvIEZlbmFjb24gUkZCIEcyMB4XDTEzMDIxNTAwMDAwMFoXDTE0MDIxNDIzNTk1OVowggEFMQswCQYDVQQGEwJCUjETMBEGA1UEChQKSUNQLUJyYXNpbDELMAkGA1UECBMCU0MxFzAVBgNVBAcUDkpBUkFHVUEgRE8gU1VMMTYwNAYDVQQLFC1TZWNyZXRhcmlhIGRhIFJlY2VpdGEgRmVkZXJhbCBkbyBCcmFzaWwgLSBSRkIxFjAUBgNVBAsUDVJGQiBlLUNOUEogQTExJTAjBgNVBAsUHEF1dGVudGljYWRvIHBvciBBUiBTZXNjb24gU0MxRDBCBgNVBAMTO0ZPUk1BIEUgRk9STUEgSU5EVVNUUklBIE1FVEFMVVJHSUNBIExUREEgRVBQOjA4MzY1MjkwMDAwMTg5MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA61Yki/lP3CkSJrhdHpWU3YCzhnEL+yofXyU/mPyd2VPZToyJkCcuDSY91fygW2Vn9tKAHOGOmL/Zbe0+Nl/CnnTUeDyZymqBVtBvyoILo2tBInrf+QiTpIwI7ZxptIVGWr66ULsIQvB3Zwvxl47Sch0pzf4NrnBdORPRAZOxAOupWZ/JGx2NEXdz9//IyndIQTI0Yiy2yKf3OJhkbvjdrxx7eMXMA6kKIrb2bGzLSGCSKP0BM9BvpxJSX1INkOr+Rk4NZTM8MIVEFAwVGRwnYmk78S6LjZnltKCV0rraySXeNYee2nRnEYNrLcx+x1A5mCOgso0vN6IfWQLJDlblgQIDAQABo4IDZzCCA2MwgaoGA1UdEQSBojCBn6A4BgVgTAEDBKAvBC0wODAzMTk2NjU4NTk1OTg4OTAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDCgGgYFYEwBAwKgEQQPTkVMTUFSIERFIFNPVVpBoBkGBWBMAQMDoBAEDjA4MzY1MjkwMDAwMTg5oBcGBWBMAQMHoA4EDDAwMDAwMDAwMDAwMIETbWljaGVsZUBndW16LmNvbS5icjAJBgNVHRMEAjAAMB8GA1UdIwQYMBaAFOx6W8+GSIO3AxW1yU1G1txadRbdMA4GA1UdDwEB/wQEAwIF4DCCASsGA1UdHwSCASIwggEeMF6gXKBahlhodHRwOi8vaWNwLWJyYXNpbC5hY2ZlbmFjb24uY29tLmJyL3JlcG9zaXRvcmlvL2xjci9BQ0luc3RpdHV0b0ZlbmFjb25SRkJHMi9MYXRlc3RDUkwuY3JsMF2gW6BZhldodHRwOi8vaWNwLWJyYXNpbC5vdXRyYWxjci5jb20uYnIvcmVwb3NpdG9yaW8vbGNyL0FDSW5zdGl0dXRvRmVuYWNvblJGQkcyL0xhdGVzdENSTC5jcmwwXaBboFmGV2h0dHA6Ly9yZXBvc2l0b3Jpby5pY3BicmFzaWwuZ292LmJyL2xjci9DZXJ0aXNpZ24vQUNJbnN0aXR1dG9GZW5hY29uUkZCRzIvTGF0ZXN0Q1JMLmNybDCBhgYDVR0gBH8wfTB7BgZgTAECASIwcTBvBggrBgEFBQcCARZjaHR0cDovL2ljcC1icmFzaWwuYWNmZW5hY29uLmNvbS5ici9yZXBvc2l0b3Jpby9kcGMvQUMtSW5zdGl0dXRvLUZlbmFjb24tUkZCL0RQQ19BQ19JRmVuYWNvbl9SRkIucGRmMB0GA1UdJQQWMBQGCCsGAQUFBwMCBggrBgEFBQcDBDCBoAYIKwYBBQUHAQEEgZMwgZAwZAYIKwYBBQUHMAKGWGh0dHA6Ly9pY3AtYnJhc2lsLmFjZmVuYWNvbi5jb20uYnIvcmVwb3NpdG9yaW8vY2VydGlmaWNhZG9zL0FDX0luc3RpdHV0b19GZW5hY29uX1JGQi5wN2MwKAYIKwYBBQUHMAGGHGh0dHA6Ly9vY3NwLmNlcnRpc2lnbi5jb20uYnIwDQYJKoZIhvcNAQELBQADggIBAF6hk6UQ1KRAdn+B1lTkAo48rVj+D7exkwZIb74B9yOciH15ltpS8mOLJzQ7KWfe/ea1oc/DwiEXesLL1b8G96QNQji0e53aMvZqWtQU+91LgGi0QGNWTRYaOLgmENdQigG7BE6R7l9I3/DT3tLYqjCZUV1iJhdy5uqNiWFerLymhHAzw0xX2XI+9ySkNVBp2dHHdehb/V+QLvQ6GKXE08e+m2Sy4jKp27guAQA6cwQBRWBfpJq3iSnlHWsOy+29U8b1Zo7qZMqCjhRP7f77T+nhSr7j5852zMdu1t6vjZZ0+6yT8whyNjES771esKrDo+ogbbPygK7f3YohzDDVOiNSB4Ms5vhV4JsXX3BnFL5HKpGa9piDjrmSsgkfWkQHfUXytgdtMcwdutcs5fXvJNDhvFQFyQg44B11o2Kx1IFsPOAMZEDM+XtzDkZTKLWzRouc/a1JfwuazHNYQAnY6c999p+yLvhgCOELsXhpsevlchlj3hgtPCoag4H9LiuVsXBv2cE/KVC+lwvD5uEmr/T4+oA/i0dx0mbNTDQubBA+y2FXa1aA6q6XCUZDiEQbrFDo1ANQE0vrDGXmKWHRPUVmvIj8587kBzwHEA8D2op7zm4ZwyPe1ibXEOAynu3dDcBkKrzr9qHJ1UDyNegQUg/m3GA9B92rQRezw0AkoNxD</X509Certificate></X509Data></KeyInfo></Signature></NFe>
	                    <protNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="2.00"><infProt Id="NFe342130061105875"><tpAmb>1</tpAmb><verAplic>SVRS20130613092133</verAplic><chNFe>42130608365290000189550020000016231328725352</chNFe><dhRecbto>2013-06-13T11:14:38</dhRecbto><nProt>342130061105875</nProt><digVal>SPtoZ9foKO3Td8nn0dv8yK+tvyc=</digVal><cStat>100</cStat><xMotivo>Autorizado o uso da NF-e</xMotivo></infProt></protNFe></nfeProc>
                    """
        #nota=''
        self.import_nfe_for_athachment(cr, uid, context, nota)
	return True
        
    def message_new(self, cr, uid, msg_dict, custom_values=None, context=None):
        
        ret = super(nfe_email, self).message_new(cr, uid, msg_dict, custom_values=custom_values, context=context)
        
        anexos = msg_dict['attachments']
        if anexos:
            for item in anexos:
                
                self.import_nfe_for_athachment(cr, uid, context=context, athachment= item[1])
        return ret


    def message_update(self, cr, uid, ids, msg_dict, vals={}, default_act=None, context=None):
        ret = super(nfe_email, self).message_update(self, cr, uid, ids, msg_dict, vals=vals, default_act=default_act, context=context)
        
        anexos = msg_dict['attachments']
        if anexos:
            for item in anexos:
                
                self.import_nfe_for_athachment(cr, uid, context=context, athachment= item[1])
        return ret


    def import_nfe_for_athachment(self,cr,uid,context=None,athachment=None):
        cfop_obj = self.pool.get('l10n_br_account.cfop')
        fo_obj = self.pool.get('l10n_br_account.fiscal.operation')
        fc_obj = self.pool.get('account.product.fiscal.classification')
        obj_address = self.pool.get('res.partner.address')
        
        try:
            LOGGER.notifyChannel(
                                 _("agtis_nfe_edocmanager"),
                                 netsvc.LOG_INFO,
                                 _("Init NFe import"))
            
            obj_user = self.pool.get('res.users').browse(cr, uid, [uid], context=context)[0]
            for company in obj_user.company_ids:
                
                if not '<NFe xmlns="http://www.portalfiscal.inf.br/nfe">' in athachment:
                    return True
                
                xml_doc = libxml2.parseDoc(athachment)
            
                xmlcontext_nfe = xml_doc.xpathNewContext()
                xmlcontext_nfe.xpathRegisterNs('nfe', 'http://www.portalfiscal.inf.br/nfe')
                
                #Informações da Nota Fical 
                nNF = xmlcontext_nfe.xpathEval("/nfe:nfeProc/nfe:NFe/nfe:infNFe/nfe:ide/nfe:nNF")[0].content
                serie = xmlcontext_nfe.xpathEval("/nfe:nfeProc/nfe:NFe/nfe:infNFe/nfe:ide/nfe:serie")[0].content
                dEmi = xmlcontext_nfe.xpathEval("/nfe:nfeProc/nfe:NFe/nfe:infNFe/nfe:ide/nfe:dEmi")[0].content
                
                #Informações do Emitente
                emit_CNPJ = xmlcontext_nfe.xpathEval("/nfe:nfeProc/nfe:NFe/nfe:infNFe/nfe:emit/nfe:CNPJ")[0].content
                emit_IE = xmlcontext_nfe.xpathEval("/nfe:nfeProc/nfe:NFe/nfe:infNFe/nfe:emit/nfe:IE")[0].content
                xFant = xmlcontext_nfe.xpathEval("/nfe:nfeProc/nfe:NFe/nfe:infNFe/nfe:emit/nfe:xFant")[0].content
                xNome = xmlcontext_nfe.xpathEval("/nfe:nfeProc/nfe:NFe/nfe:infNFe/nfe:emit/nfe:xNome")[0].content
                xLgr = xmlcontext_nfe.xpathEval("/nfe:nfeProc/nfe:NFe/nfe:infNFe/nfe:emit/nfe:enderEmit/nfe:xLgr")[0].content
                nro = xmlcontext_nfe.xpathEval("/nfe:nfeProc/nfe:NFe/nfe:infNFe/nfe:emit/nfe:enderEmit/nfe:nro")[0].content
                xBairro = xmlcontext_nfe.xpathEval("/nfe:nfeProc/nfe:NFe/nfe:infNFe/nfe:emit/nfe:enderEmit/nfe:xBairro")[0].content
                cMun = xmlcontext_nfe.xpathEval("/nfe:nfeProc/nfe:NFe/nfe:infNFe/nfe:emit/nfe:enderEmit/nfe:cMun")[0].content
                CEP = xmlcontext_nfe.xpathEval("/nfe:nfeProc/nfe:NFe/nfe:infNFe/nfe:emit/nfe:enderEmit/nfe:CEP")[0].content
                fone = xmlcontext_nfe.xpathEval("/nfe:nfeProc/nfe:NFe/nfe:infNFe/nfe:emit/nfe:enderEmit/nfe:fone")[0].content
                
                #Itens da nota
                itens_nota = xmlcontext_nfe.xpathEval("/nfe:nfeProc/nfe:NFe/nfe:infNFe/nfe:det")
                
                
                
                #Informações do Destinatario
                dest_CNPJ = xmlcontext_nfe.xpathEval("/nfe:nfeProc/nfe:NFe/nfe:infNFe/nfe:dest/nfe:CNPJ")[0].content
            
                
                #Dados do processamento da NFe na receita
                chNFe = xmlcontext_nfe.xpathEval("/nfe:nfeProc/nfe:protNFe/nfe:infProt/nfe:chNFe")[0].content
                dhRecbto = xmlcontext_nfe.xpathEval("/nfe:nfeProc/nfe:protNFe/nfe:infProt/nfe:dhRecbto")[0].content
                xMotivo = xmlcontext_nfe.xpathEval("/nfe:nfeProc/nfe:protNFe/nfe:infProt/nfe:xMotivo")[0].content
                
                obj_invoice = self.pool.get('account.invoice')
                obj_partner = self.pool.get('res.partner')
            
                
                emit_CNPJ = re.sub('[^0-9]', '', emit_CNPJ)
                if len(emit_CNPJ) == 14:
                    emit_CNPJ = "%s.%s.%s/%s-%s" % (emit_CNPJ[0:2], emit_CNPJ[2:5], emit_CNPJ[5:8], emit_CNPJ[8:12], emit_CNPJ[12:14])
                    
                dest_CNPJ = re.sub('[^0-9]', '', dest_CNPJ)
                if len(dest_CNPJ) == 14:
                    dest_CNPJ = "%s.%s.%s/%s-%s" % (dest_CNPJ[0:2], dest_CNPJ[2:5], dest_CNPJ[5:8], dest_CNPJ[8:12], dest_CNPJ[12:14])
                    
                
                #Criando Endereço
                address_id=None
                cr.execute("""SELECT
                                id city_id
                                ,state_id
                                FROM l10n_br_base_city
                                WHERE ibge_code = '%s'
                                AND state_id = (SELECT id 
                                                  FROM res_country_state
                                                 WHERE ibge_code = '%s'
                                                  )""" %(cMun[2:],cMun[0:2]) ) 
                        
                state_city = cr.dictfetchone()
                vals_end={}
                if state_city:
                    vals_end = {'type':'default',
                            'street':xLgr,
                            'number':nro,
                            'district':xBairro,
                            'zip':CEP,
                            'country_id':32,#id do brasil
                            'phone':fone,
                            'state_id':state_city['state_id'],
                            'l10n_br_city_id':state_city['city_id'],
                            }
        
                
                if company.partner_id.cnpj_cpf == dest_CNPJ:
                    
                    list_ids= obj_partner.search(cr,uid,args=[('cnpj_cpf','=',emit_CNPJ)])
                    
                    #CADASTRO DO NOVO CLIENTE
                                        
                    
                    if not list_ids:
                        vals_cli = {'name':xFant,
                                'legal_name':xNome,
                                'cnpj_cpf':emit_CNPJ,
                                'costomer':True,
                                'supplier':True,
                                'inscr_est':emit_IE}
                        partner_id = obj_partner.create(cr,uid,vals=vals_cli)
            
                        vals_end.update({'partner_id':partner_id})
                        
                        address_id=obj_address.create(cr,uid,vals=vals_end)
                    else:
                        partner_id = list_ids[0]
                        
                        if state_city:
                            address_id = obj_address.search(cr,uid,args=[('street','=',xLgr),('district','=',xBairro),('zip','=',CEP),('number','=',nro),('state_id','=',state_city['state_id']),('l10n_br_city_id','=',state_city['city_id'])])
                            if not address_id:
                                vals_end.update({'partner_id':partner_id})
                                address_id=obj_address.create(cr,uid,vals=vals_end)
                    
            
                    if  isinstance(address_id, list):
                        address_id = address_id[0] 
                    

                    partner = obj_partner.browse(cr,uid,partner_id)

		    
                    #CRIANDO FATURA DE ENTRADA

                    foc_id_capa = False
                    fo_id_capa = False
                    
                    obj_journal = self.pool.get('account.journal')
                    obj_account = self.pool.get('account.account')
                    obj_currency = self.pool.get('res.currency')
                    obj_fdocument = self.pool.get('l10n_br_account.fiscal.document')
                    journal_id = obj_journal.search(cr,uid,args=[('code','like','DC')])
                    account_id = obj_account.search(cr,uid,args=[('name','like','%Fornecedores Nacionais%')])
                    curruency_id = obj_currency.search(cr,uid,args=[('name','like','%BRL%')])
                    fd = obj_fdocument.search(cr,uid,args=[('code','=','55')])
                    
                    
                    vals = {'journal_id':journal_id[0],
                            'date_invoice':dEmi,
                            'internal_number':nNF,
                            'vendor_serie':serie,
                            'partner_id':partner_id,
                            'address_invoice_id': address_id,
                            'own_invoice':False,
                            'account_id':account_id[0],#id conta padrao
                            'currency_id':curruency_id[0],# id moeda brasileira
                            'state':'draft',
                            'company_id':company.id,
                            'fiscal_type':'product',
                            'nfe_access_key':chNFe,
                            'nfe_status':xMotivo,
                            'nfe_export_date':dhRecbto,
                            'fiscal_document_id':fd[0],
                            'ind_is_shipment':True
                            }
                    
                    invoice_id = obj_invoice.create(cr,uid,vals=vals,context={'type':'in_invoice'})
                    invoice = obj_invoice.browse(cr,uid,invoice_id)
                    
                    
                    
                    obj_product = self.pool.get('product.product')
                    obj_invoice_line = self.pool.get('account.invoice.line')
                    obj_supplier = self.pool.get('product.supplierinfo')
                    obj_uom = self.pool.get('product.uom')
                    
                    for item in itens_nota:
                        
                        xmlcontext_nfe.setContextNode(item)
                        
                        xProd = xmlcontext_nfe.xpathEval("nfe:prod/nfe:xProd")[0].content
                        cProd = xmlcontext_nfe.xpathEval("nfe:prod/nfe:cProd")[0].content
                        
                        NCM = xmlcontext_nfe.xpathEval("nfe:prod/nfe:NCM")[0].content
                        
                        #VERIFICA E CRIA CLASSIFICAÇÃO FISCAL
                        fc_id = False
                        cr.execute(""" SELECT id
                                        FROM account_product_fiscal_classification
                                        WHERE replace(name,'.','') like '%s'
                                        """ % NCM)
                        fc_id = cr.dictfetchone()
                        if fc_id:
                            fc_id = fc_id['id']
                        else:
                            fc_id = fc_obj.create(cr, uid, {'name':NCM,
                                                            'description':NCM,
                                                            'company_id':company.id
                                                            })
                        
                         
                        #VERIFICA E CRIA UNIDADE DE MEDIDA
                        unidade = xmlcontext_nfe.xpathEval("nfe:prod/nfe:uCom")[0].content
                        
                        uom_id = obj_uom.search(cr,uid,args = [('name','=',unidade)])
                        
                        if not uom_id :
                            uom_id = obj_uom.create(cr,uid,{'category_id':1,
                                                             'name':unidade,
                                                             'rounding':1.0,
                                                             'factor':1.0})
                        else:
                            uom_id =  uom_id[0]
                        
            
                        #VERIFICA E CRIA  PRODUTOS
                        cr.execute("""SELECT 
                                       id
                                       FROM product_product prod
                                       WHERE
                                        default_code = '%s'
                                         AND (SELECT count(id)
                                                FROM product_supplierinfo
                                               WHERE name = %s
                                                 AND product_code = '%s')>0
                                      LIMIT 1  """ %(cProd,partner_id,cProd))
            
                        
                        
                        product_id = cr.dictfetchone()
            
                        if not product_id:
                            prod_vals = {'default_code':cProd,
                                         'name': xProd,
                                         'property_fiscal_classification':fc_id,
                                         'uom_id':uom_id,
                                         'uom_po_id':uom_id,
                                         'list_price':0.01,
                                         'standard_price':0.01,
                                         'price_margin':0.0,
                                         }
                            product_id = obj_product.create(cr,uid,prod_vals)
                            product = obj_product.browse(cr,uid,product_id)
            
                            supplier_vals = {'name':partner_id,
                                            'product_id':product.product_tmpl_id.id,
                                            'min_qty':0,
                                            'delay':1,
                                            'product_code':cProd,
                                            'product_name':xProd,}
                            
                            obj_supplier.create(cr,uid,supplier_vals)
            
                        else:
                            product = obj_product.browse(cr,uid,product_id['id'])
                            product.write({'name':xProd,
                                           'property_fiscal_classification':fc_id})
            
                        #CRIANDO LINHAS DA FATURA
                        
                        foc_id = False
                        fo_id = False
                        cfop_id= False
                        
                        cfop = xmlcontext_nfe.xpathEval("nfe:prod/nfe:CFOP")[0].content
                        if cfop[0:1] in '567':
                            if cfop[0:1]=='5': cfop='1'+cfop[1:]
                            if cfop[0:1]=='6': cfop='2'+cfop[1:]
                            if cfop[0:1]=='7': cfop='3'+cfop[1:]
                        
                                
                            
                        cfop_id = cfop_obj.search(cr, uid, args=[('code','=',cfop)])
                        if cfop_id:
                            cfop_id=cfop_id[0]
                        
                        if cfop in ['1901','2901','3901']:
                            
                            fo_id = fo_obj.search(cr, uid, args=[('cfop_id','=',cfop_id)])
                            if fo_id:
                                if isinstance(fo_id, list):
                                    fo_id = fo_id[0]
                                fo_brw = fo_obj.browse(cr,uid,fo_id)
                                foc_id = fo_brw.fiscal_operation_category_id.id
                            foc_id_capa = foc_id
                            fo_id_capa = fo_id
                        
                        icms_tipo = []
                        ipi_tipo = []
                        pis_tipo = []
                        cofins_tipo = []

                        try:
                            icms_tipo = xmlcontext_nfe.xpathEval("nfe:imposto/nfe:ICMS")[0].children
                        except:
			                pass
                        
                        try:
                            ipi_tipo = xmlcontext_nfe.xpathEval("nfe:imposto/nfe:IPI")[0]
                        except:
			                pass

                        try:
                            pis_tipo = xmlcontext_nfe.xpathEval("nfe:imposto/nfe:PIS")[0].children
                        except:
			                pass

                        try:
                            cofins_tipo = xmlcontext_nfe.xpathEval("nfe:imposto/nfe:COFINS")[0].children
                        except:
			                pass
                        
                        
                        
            
                        
                        
                        cst_icms_st, base_calc_icms_st, val_icms_st, aliq_icms_st = [None,None,None,None]
                        cst_icms, base_calc_icms,val_icms, aliq_icms = [None,None,None,None]
                        cst_ipi, base_calc_ipi, val_ipi,aliq_ipi = [None,None,None,None]
                        cst_pis, base_calc_pis, val_pis,aliq_pis = [None,None,None,None]
                        cst_cofins, base_calc_cofins, val_cofins,aliq_cofins = [None,None,None,None]
                        
                        
                        obj_fiscal_type = self.pool.get('l10n_br_account.partner.fiscal.type')
                        contribuinte_id,simples_id = [None,None]

                        for item_icms in icms_tipo:
                            if icms_tipo.name == "ICMSST":
                                if item_icms.name == "CSOSN":
                                    cst_icms_st = item_icms.content
                                    simples_id = obj_fiscal_type.search(cr,uid,args=[('code','=','Simples Nacional')])[0]
                                if  item_icms.name == "CST":
                                    cst_icms_st = item_icms.content
                                    contribuinte_id = obj_fiscal_type.search(cr,uid,args=[('code','=','Contribuinte')])[0]

                                if item_icms.name == "vBCSTRet":
                                    base_calc_icms_st = item_icms.content
                                if item_icms.name == "vICMSSTRet":
                                    val_icms_st = item_icms.content
                                if item_icms.name == "pICMS":
                                    aliq_icms_st = item_icms.content
                            else:
                                
                                if item_icms.name == "CSOSN":
                                    cst_icms_st = item_icms.content
                                    simples_id = obj_fiscal_type.search(cr,uid,args=[('code','=','Simples Nacional')])[0]
                                                                    
                                if  item_icms.name == "CST":
                                    cst_icms_st = item_icms.content
                                    contribuinte_id = obj_fiscal_type.search(cr,uid,args=[('code','=','Contribuinte')])[0]
                                    
                                if item_icms.name == "vBC":
                                    base_calc_icms = item_icms.content
                                if item_icms.name == "vICMS":
                                    val_icms = item_icms.content
                                if item_icms.name == "pICMS":
                                    aliq_icms = item_icms.content
                        
                               
                        for item_ipi in ipi_tipo:
                            if item_ipi.name == "IPINT" or item_ipi.name == "IPITrib ":
                                for  values in item_ipi:
                                    if values.name == "CST":
                                        cst_ipi = values.content
                                    if values.name == "vBC":
                                        base_calc_ipi = values.content
                                    if values.name == "vIPI":
                                        val_ipi = values.content
                                    if values.name == "pIPI":
                                        aliq_ipi = values.content
                                break
                        
                        for item_pis in pis_tipo:
                            if item_pis.name == "CST":
                                cst_pis = item_pis.content
                            if item_pis.name == "vBC":
                                base_calc_pis = item_pis.content
                            if item_pis.name == "vPIS":
                                val_pis = item_pis.content
                            if item_pis.name == "pPIS":
                                aliq_pis = item_pis.content
                                
                        for item_cofins in cofins_tipo:
                            if item_cofins.name == "CST":
                                cst_cofins = item_cofins.content
                            if item_cofins.name == "vBC":
                                base_calc_cofins = item_cofins.content
                            if item_cofins.name == "vCOFINS":
                                val_cofins = item_cofins.content
                            if item_cofins.name == "pCOFINS":
                                aliq_cofins = item_cofins.content

                        if not partner.partner_fiscal_type_id:
                                                        
                            if simples_id:
                                partner.write({'partner_fiscal_type_id': simples_id})
                                
                            if contribuinte_id:
                                partner.write({'partner_fiscal_type_id': contribuinte_id})
                                
                        
                        quantity = float(xmlcontext_nfe.xpathEval("nfe:prod/nfe:qCom")[0].content)
                        price_unit = float(xmlcontext_nfe.xpathEval("nfe:prod/nfe:vUnCom")[0].content)
                        per_discount = 0
                        val_discount = 0
                        
                        
                        
                        price_subtotal =  (quantity * price_unit)-val_discount
                        price_total = quantity * price_unit
                        account_line_id = obj_account.search(cr,uid,args=[('name','like','%Custo dos Produtos Acabados%')])[0]
                        line_vals = {'product_id':product.id,
                                     'name':product.name,
                                     'quantity':quantity,
                                     'price_unit':price_unit,
                                     'discount':per_discount,
                                     'price_subtotal': price_subtotal,
                                     'price_total': price_total,
                                     'invoice_id': invoice.id,
                                     'fiscal_operation_category_id':foc_id,
                                     'fiscal_operation_id':fo_id,
                                     'cfop_id':cfop_id,
                                     'account_id':account_line_id, 
                                     'uos_id':uom_id,
                                     'calculate_taxes':False
                                     }
                        
                        
                        line_id = obj_invoice_line.create(cr,uid,line_vals)
                        
                        invoice_line = obj_invoice_line.browse(cr,uid,line_id)

                        
                        fiscal_values = {   'icms_cst':cst_icms,
                                             'icms_base':base_calc_icms,
                                             'icms_value':val_icms,
                                             'icms_percent': aliq_icms,
                                             'icms_st_cst':cst_icms_st,
                                             'icms_st_base':base_calc_icms_st,
                                             'icms_st_value':val_icms_st,
                                             'icms_st_percent':aliq_icms_st,
                                             'ipi_cst':cst_ipi,
                                             'ipi_base':base_calc_ipi,
                                             'ipi_value':val_ipi,
                                             'ipi_percent': aliq_ipi,
                                             'pis_cst':cst_pis,
                                             'pis_base':base_calc_pis,
                                             'pis_value':val_pis,
                                             'pis_percent':aliq_pis,
                                             'cofins_cst':cst_cofins,
                                             'cofins_base':base_calc_cofins,
                                             'cofins_value':val_cofins,
                                             'cofins_percent': aliq_cofins,
                                             'fiscal_operation_category_id':foc_id,
                                             'fiscal_operation_id':fo_id,
                                             'cfop_id':cfop_id,
                                             }

                        invoice_line.write(fiscal_values)
                    if foc_id_capa:
                        
                        invoice.write({                    
                            'fiscal_operation_category_id':foc_id_capa,
                            'fiscal_operation_id':fo_id_capa,
                            'account_id': fo_brw.account_id.id,
                            'jornal_id':fo_brw.fiscal_operation_category_id.journal_ids[0].id ,
                            })
                        

                        
                

        except Exception, e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            LOGGER.notifyChannel(
                                 _("agtis_nfe_edocmanager"),
                                 netsvc.LOG_ERROR,
                                 _("Error Importing NFe: %s\nTipo: %s\nArquivo: %s\nLinha %s) " % (str(e), exc_type, fname , exc_tb.tb_lineno))
                                )
nfe_email()




class account_fiscal_position_rule(osv.osv):
    _inherit = 'account.fiscal.position.rule'

    def fiscal_position_map(self, cr, uid, partner_id=False, partner_invoice_id=False, company_id=False, fiscal_operation_category_id=False, context=None, fiscal_operation_id=False):
        print "k------------------------ fiscal_position_map fiscal_rule entrada "

        #Initiate variable result
        result = {'fiscal_position': False, 'fiscal_operation_id': False}

        if partner_id == False or not partner_invoice_id or company_id == False or fiscal_operation_category_id == False:
             return result

        obj_partner = self.pool.get("res.partner").browse(cr, uid, partner_id)
        obj_company = self.pool.get("res.company").browse(cr, uid, company_id)
		
        #Case 1: If Partner has Specific Fiscal Posigion
        if obj_partner.property_account_position.id:
            result['fiscal_position'] = obj_partner.property_account_position.id
            result['fiscal_operation_id'] = obj_partner.property_account_position.fiscal_operation_id.id
            return result
		
		#Case 2: Search fiscal position using Account Fiscal Position Rule
        company_addr = self.pool.get('res.partner').address_get(cr, uid, [obj_company.partner_id.id], ['default'])
        company_addr_default = self.pool.get('res.partner.address').browse(cr, uid, [company_addr['default']])[0]
        
        from_country = company_addr_default.country_id.id
        from_state = company_addr_default.state_id.id

        if not partner_invoice_id:
            partner_addr = self.pool.get('res.partner').address_get(cr, uid, [obj_partner.id], ['invoice'])
            partner_addr_default = self.pool.get('res.partner.address').browse(cr, uid, [partner_addr['invoice']])[0]
        else:
            partner_addr_default = self.pool.get('res.partner.address').browse(cr, uid, partner_invoice_id)

        to_country = partner_addr_default.country_id.id
        to_state = partner_addr_default.state_id.id
        
        document_date = context.get('date', time.strftime('%Y-%m-%d'))
        
        use_domain = context.get('use_domain', ('use_sale', '=', True))
        
        domain = ['&', ('company_id', '=', company_id), 
                  ('fiscal_operation_category_id', '=', fiscal_operation_category_id), 
                  use_domain,
                  ('fiscal_type', '=', obj_company.fiscal_type),
                  '|', ('from_country','=',from_country), ('from_country', '=', False), 
                  '|', ('to_country', '=', to_country), ('to_country', '=', False), 
                  '|', ('from_state', '=', from_state), ('from_state', '=', False), 
                  '|', ('to_state','=', to_state), ('to_state', '=', False),
                  '|', ('date_start', '=', False), ('date_start', '<=', document_date),
                  '|', ('date_end', '=', False), ('date_end', '>=', document_date),
                  '|', ('revenue_start', '=', False), ('revenue_start', '<=', obj_company.annual_revenue),
                  '|', ('revenue_end', '=', False), ('revenue_end', '>=', obj_company.annual_revenue),]
        if fiscal_operation_id:
            valid_fiscal_position_ids = self.pool.get('account.fiscal.position').search(cr, uid, args=[('fiscal_operation_id','=',fiscal_operation_id)])
            print "m-------------------------------- valid_fiscal_position_ids = ", pprint(valid_fiscal_position_ids)
            domain.append(('fiscal_position_id','in',valid_fiscal_position_ids))
        
        #print "------------------------ fiscal_position_map fiscal_rule domains is "
        #pprint(domain)

        fsc_pos_id = self.search(cr, uid, domain)
        
        if fsc_pos_id:
            obj_fpo_rule = self.pool.get('account.fiscal.position.rule').browse(cr, uid, fsc_pos_id)[0]
            result['fiscal_position'] = obj_fpo_rule.fiscal_position_id.id
            result['fiscal_operation_id'] = obj_fpo_rule.fiscal_position_id.fiscal_operation_id.id
        
        return result

account_fiscal_position_rule()



